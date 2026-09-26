"""Sequential interactive-salloc orchestrator logic (testable; runs on NERSC)."""

from __future__ import annotations  # Required for Optional[Callable[...]] on Perlmutter 3.8

import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from blast_lib.iterative_loop.slurm_job_state import (
    fetch_sacct_job_state_local,
    slurm_state_is_terminal,
    slurm_state_ok_after_gpu_walltime,
)

from blast_lib.iterative_loop.ho_report_local import count_scored_trials
from blast_lib.iterative_loop.range_core import run_range_update_local
from blast_lib.iterative_loop.range_types import RangeUpdateResult
from blast_lib.iterative_loop.remote_workflow import (
    WorkflowPhase,
    WorkflowStatus,
    cycle_before_path,
    cycle_range_result_path,
    load_workflow,
    save_workflow,
    workflow_json_path,
    write_json_atomic,
)
from blast_lib.iterative_loop.salloc_command import SallocSettings, build_interactive_runbop_shell
from blast_lib.iterative_loop.slurm_env import clear_inherited_slurm_env

_SALLOC_JOB_RE = re.compile(r"Granted job allocation (\d+)", re.I)

_CRON_MAX_SECONDS = 24 * 3600 - 300  # 23h55m — Perlmutter cron QOS 24h cap with slack


def walltime_hms_to_seconds(hms: str) -> int:
    text = hms.strip()
    if "-" in text:
        day_part, rest = text.split("-", 1)
        days = int(day_part)
        parts = rest.split(":")
    else:
        days = 0
        parts = text.split(":")
    if len(parts) == 2:
        h, m = (int(parts[0]), int(parts[1]))
        s = 0
    elif len(parts) == 3:
        h, m, s = (int(parts[0]), int(parts[1]), int(parts[2]))
    else:
        raise ValueError(f"Invalid walltime: {hms!r}")
    return days * 86400 + h * 3600 + m * 60 + s


def seconds_to_slurm_time(sec: int) -> str:
    sec = max(60, sec)
    days, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if days:
        return f"{days}-{h:02d}:{m:02d}:{s:02d}"
    return f"{h:02d}:{m:02d}:{s:02d}"


def estimate_orchestrator_cron_walltime(
    *,
    total_cycles: int,
    cycle_walltime: str,
    margin_hours: float = 2.0,
) -> str:
    """Cron job walltime: cycles × GPU walltime + margin (capped at ~24h)."""
    per = walltime_hms_to_seconds(cycle_walltime)
    need = int(total_cycles * per + margin_hours * 3600 + 1800)  # 30m Range slack
    capped = min(need, _CRON_MAX_SECONDS)
    return seconds_to_slurm_time(capped)


def parse_salloc_job_id(output: str) -> str | None:
    match = _SALLOC_JOB_RE.search(output or "")
    return match.group(1) if match else None


def salloc_settings_from_workflow(wf) -> SallocSettings:
    return SallocSettings(
        blast_root=wf.blast_root,
        walltime=wf.walltime,
        account=wf.gpu_account or wf.salloc_account,
        nodes=int(wf.salloc_nodes or 2),
        ntasks_per_node=int(wf.salloc_ntasks_per_node or 4),
        gpus_per_task=int(wf.salloc_gpus_per_task or 1),
        gpus=int(wf.salloc_gpus or 8),
        qos=wf.salloc_qos or "interactive",
    )


@dataclass
class SallocRunResult:
    returncode: int
    combined_output: str
    job_id: str | None


OnSallocGranted = Optional[Callable[[str], None]]
ShouldAbort = Optional[Callable[[], bool]]
PollSlurmJobState = Callable[[str], Optional[str]]

@dataclass
class OrchestratorHooks:
    """Injected dependencies for tests and the live orchestrator script."""

    run_shell: Callable[..., SallocRunResult]
    run_range: Callable[[Path, str, int, str, str], RangeUpdateResult]
    count_trials: Callable[[Path], int]
    sleep: Callable[[float], None]
    load_workflow: Callable[[Path], Any]
    save_workflow: Callable[[Path, Any], None]
    env: dict[str, str]
    salloc_retry_sleep_sec: float = 120.0
    max_salloc_attempts_per_cycle: int | None = None


def _fail(wf_path: Path, wf, hooks: OrchestratorHooks, message: str) -> int:
    wf.status = WorkflowStatus.FAILED
    wf.phase = WorkflowPhase.FAILED
    wf.error = message
    wf.status_message = message
    hooks.save_workflow(wf_path, wf)
    return 1


def _stopped(wf_path: Path, wf, hooks: OrchestratorHooks) -> bool:
    fresh = hooks.load_workflow(wf_path)
    if fresh.status == WorkflowStatus.STOPPED or fresh.phase == WorkflowPhase.STOPPED:
        hooks.save_workflow(wf_path, fresh)
        return True
    return False


def run_one_cycle(
    wf_path: Path,
    wf,
    cycle: int,
    *,
    step_b: str,
    hooks: OrchestratorHooks,
) -> tuple[bool, Any]:
    """
    Run one cycle. Returns (ok, updated_wf).
    On failure wf is marked FAILED unless stop requested.
    """
    run_folder = Path(wf.run_folder)
    rec = wf.cycle_record(cycle)
    wf.current_cycle = cycle
    wf.phase = WorkflowPhase.AWAITING_SALLOC
    wf.status = WorkflowStatus.RUNNING
    wf.status_message = f"Cycle {cycle}/{wf.total_cycles}: awaiting interactive GPU…"
    hooks.save_workflow(wf_path, wf)

    if _stopped(wf_path, wf, hooks):
        return False, hooks.load_workflow(wf_path)

    rp = run_folder / "reports" / "ho.report"
    before = hooks.count_trials(rp)
    rec.scored_trials_before = before
    write_json_atomic(
        cycle_before_path(run_folder, cycle),
        {"cycle": cycle, "scored_trials_before": before},
    )
    hooks.save_workflow(wf_path, wf)

    settings = salloc_settings_from_workflow(wf)
    shell_cmd = build_interactive_runbop_shell(settings, step_b=step_b)
    attempts = 0

    while True:
        if _stopped(wf_path, wf, hooks):
            return False, hooks.load_workflow(wf_path)

        attempts += 1
        wf.salloc_attempts = (wf.salloc_attempts or 0) + 1
        wf.phase = WorkflowPhase.AWAITING_SALLOC
        wf.status_message = f"Cycle {cycle}: requesting salloc (attempt {attempts})…"
        hooks.save_workflow(wf_path, wf)

        child_env = clear_inherited_slurm_env(hooks.env)
        wf.phase = WorkflowPhase.RUNNING_GPU
        hooks.save_workflow(wf_path, wf)

        def _on_salloc_granted(job_id: str) -> None:
            live = hooks.load_workflow(wf_path)
            live_rec = live.cycle_record(cycle)
            live_rec.gpu_job_id = job_id
            live.current_interactive_job_id = job_id
            live.phase = WorkflowPhase.RUNNING_GPU
            live.status_message = f"Cycle {cycle}: interactive allocation {job_id} running RunBOP…"
            hooks.save_workflow(wf_path, live)

        def _should_abort() -> bool:
            return _stopped(wf_path, wf, hooks)

        result = hooks.run_shell(
            shell_cmd,
            child_env,
            _on_salloc_granted,
            should_abort=_should_abort,
        )
        wf = hooks.load_workflow(wf_path)
        rec = wf.cycle_record(cycle)
        job_id = result.job_id or rec.gpu_job_id or parse_salloc_job_id(result.combined_output)
        if job_id and not rec.gpu_job_id:
            rec.gpu_job_id = job_id
            wf.current_interactive_job_id = job_id
            hooks.save_workflow(wf_path, wf)

        if result.returncode != 0:
            msg = (
                f"salloc/RunBOP failed for cycle {cycle} (exit {result.returncode}). "
                f"{result.combined_output[-500:]}"
            )
            if hooks.max_salloc_attempts_per_cycle and attempts >= hooks.max_salloc_attempts_per_cycle:
                wf.status = WorkflowStatus.FAILED
                wf.phase = WorkflowPhase.FAILED
                wf.error = msg
                wf.status_message = msg
                hooks.save_workflow(wf_path, wf)
                return False, wf
            wf.status_message = f"{msg} Retrying after {hooks.salloc_retry_sleep_sec}s…"
            hooks.save_workflow(wf_path, wf)
            hooks.sleep(hooks.salloc_retry_sleep_sec)
            wf = hooks.load_workflow(wf_path)
            continue

        break

    wf.phase = WorkflowPhase.VALIDATING
    wf.status_message = f"Cycle {cycle}: validating GPU allocation…"
    wf.current_interactive_job_id = None
    hooks.save_workflow(wf_path, wf)

    if not rec.gpu_job_id:
        wf.status = WorkflowStatus.FAILED
        wf.phase = WorkflowPhase.FAILED
        wf.error = f"Cycle {cycle}: could not determine interactive allocation job id."
        hooks.save_workflow(wf_path, wf)
        return False, wf

    wf.phase = WorkflowPhase.RUNNING_RANGE
    wf.status_message = f"Cycle {cycle}: running Range update…"
    hooks.save_workflow(wf_path, wf)

    range_result = hooks.run_range(
        run_folder,
        wf.blast_python,
        before,
        rec.gpu_job_id,
        wf.walltime,
    )
    after = hooks.count_trials(rp)
    rec.scored_trials_after = after
    rec.last_slurm_elapsed_sec = range_result.gpu_elapsed_sec
    rec.best_score = range_result.best_score
    rec.best_iteration = range_result.best_iteration

    write_json_atomic(
        cycle_range_result_path(run_folder, cycle),
        {
            "cycle": cycle,
            "ok": range_result.ok,
            "message": range_result.message,
            "scored_trials_after": after,
            "best_score": range_result.best_score,
            "best_iteration": range_result.best_iteration,
            "gpu_elapsed_sec": range_result.gpu_elapsed_sec,
        },
    )

    if not range_result.ok:
        rec.range_status = "FAILED"
        rec.error = range_result.message
        wf.status = WorkflowStatus.FAILED
        wf.phase = WorkflowPhase.FAILED
        wf.error = range_result.message
        wf.status_message = f"Range failed on cycle {cycle}."
        hooks.save_workflow(wf_path, wf)
        return False, wf

    rec.range_status = "COMPLETED"
    rec.error = None
    wf.status_message = f"Cycle {cycle}/{wf.total_cycles} complete."
    hooks.save_workflow(wf_path, wf)
    return True, wf


def run_orchestrator(
    wf_path: Path,
    *,
    step_b: str,
    hooks: OrchestratorHooks,
    start_cycle: int = 1,
) -> int:
    wf = hooks.load_workflow(wf_path)
    if wf.status == WorkflowStatus.STOPPED:
        return 0

    wf.status = WorkflowStatus.RUNNING
    wf.phase = WorkflowPhase.AWAITING_SALLOC
    hooks.save_workflow(wf_path, wf)

    for cycle in range(start_cycle, wf.total_cycles + 1):
        ok, wf = run_one_cycle(wf_path, wf, cycle, step_b=step_b, hooks=hooks)
        if not ok:
            if wf.status == WorkflowStatus.STOPPED:
                return 0
            return 1
        if cycle >= wf.total_cycles:
            wf.status = WorkflowStatus.COMPLETED
            wf.phase = WorkflowPhase.COMPLETED
            wf.status_message = f"Workflow complete — {wf.total_cycles} cycle(s) finished."
            wf.error = None
            hooks.save_workflow(wf_path, wf)
            return 0

    return 0


def _terminate_process_tree(
    proc: subprocess.Popen[str],
    *,
    grace_sec: float,
    kill_timeout_sec: float,
) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        proc.terminate()
    deadline = time.monotonic() + grace_sec
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.15)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()
    try:
        proc.wait(timeout=kill_timeout_sec)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _scancel_job_local(job_id: str) -> None:
    try:
        subprocess.run(
            ["scancel", job_id.strip()],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def stream_shell_run(
    cmd: str,
    env: dict[str, str],
    on_salloc_granted: OnSallocGranted = None,
    *,
    should_abort: ShouldAbort = None,
    poll_slurm_job_state: PollSlurmJobState | None = None,
    poll_interval_sec: float = 5.0,
    cleanup_grace_sec: float = 30.0,
    cleanup_kill_timeout_sec: float = 15.0,
) -> SallocRunResult:
    """
    Run salloc + Step B with streamed stdout (no capture_output buffer deadlock).

    Calls ``on_salloc_granted`` once as soon as Slurm prints ``Granted job allocation …``.

    After the allocation job id is known, polls sacct/squeue independently. When the Slurm
    allocation reaches a terminal state, reaps stale salloc/bash/parallel children that may
    still hold stdout open (common after interactive TIMEOUT).
    """
    poll_fn = poll_slurm_job_state or fetch_sacct_job_state_local
    proc = subprocess.Popen(
        ["/bin/bash", "-lc", cmd],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    chunks: list[str] = []
    job_id: str | None = None
    granted_called = False
    slurm_ended = False
    aborted = False
    lock = threading.Lock()

    if proc.stdout is None:
        return SallocRunResult(returncode=1, combined_output="", job_id=None)

    def _reader() -> None:
        nonlocal job_id, granted_called
        try:
            for line in proc.stdout:
                with lock:
                    chunks.append(line)
                if on_salloc_granted and not granted_called:
                    match = _SALLOC_JOB_RE.search(line)
                    if match:
                        with lock:
                            job_id = match.group(1)
                            granted_called = True
                        on_salloc_granted(job_id)
        finally:
            try:
                proc.stdout.close()
            except OSError:
                pass

    reader = threading.Thread(target=_reader, name="stream_shell_run_reader", daemon=True)
    reader.start()

    def _known_job_id() -> str | None:
        with lock:
            if job_id:
                return job_id
            return parse_salloc_job_id("".join(chunks))

    terminal_slurm_state: str | None = None
    while proc.poll() is None:
        active_job = _known_job_id()

        if should_abort and should_abort():
            aborted = True
            if active_job:
                _scancel_job_local(active_job)
            _terminate_process_tree(
                proc,
                grace_sec=cleanup_grace_sec,
                kill_timeout_sec=cleanup_kill_timeout_sec,
            )
            break

        if active_job:
            state = poll_fn(active_job)
            if state and slurm_state_is_terminal(state):
                slurm_ended = True
                terminal_slurm_state = state
                _terminate_process_tree(
                    proc,
                    grace_sec=cleanup_grace_sec,
                    kill_timeout_sec=cleanup_kill_timeout_sec,
                )
                break

        time.sleep(poll_interval_sec)

    reader.join(timeout=2.0)
    try:
        returncode = proc.wait(timeout=cleanup_kill_timeout_sec)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(
            proc,
            grace_sec=5.0,
            kill_timeout_sec=cleanup_kill_timeout_sec,
        )
        returncode = proc.wait(timeout=cleanup_kill_timeout_sec)

    with lock:
        combined = "".join(chunks)
        resolved_job = job_id or parse_salloc_job_id(combined)

    if slurm_ended and terminal_slurm_state and slurm_state_ok_after_gpu_walltime(terminal_slurm_state):
        returncode = 0
    elif aborted:
        returncode = 0
    elif slurm_ended and terminal_slurm_state and not slurm_state_ok_after_gpu_walltime(terminal_slurm_state):
        returncode = returncode if returncode else 1

    return SallocRunResult(
        returncode=returncode,
        combined_output=combined,
        job_id=resolved_job,
    )


def default_run_shell(
    cmd: str,
    env: dict[str, str],
    on_salloc_granted: OnSallocGranted = None,
    should_abort: ShouldAbort = None,
) -> SallocRunResult:
    return stream_shell_run(cmd, env, on_salloc_granted, should_abort=should_abort)


def default_hooks(env: dict[str, str] | None = None) -> OrchestratorHooks:
    import os

    base = dict(os.environ)
    return OrchestratorHooks(
        run_shell=default_run_shell,
        run_range=lambda rf, py, before, jid, wt: run_range_update_local(
            rf, py, scored_before=before, gpu_job_id=jid, walltime=wt
        ),
        count_trials=lambda rp: count_scored_trials(rp),
        sleep=time.sleep,
        load_workflow=load_workflow,
        save_workflow=save_workflow,
        env=env if env is not None else base,
    )
