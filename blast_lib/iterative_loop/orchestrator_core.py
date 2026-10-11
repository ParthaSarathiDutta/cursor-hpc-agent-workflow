"""Sequential interactive-salloc orchestrator logic (testable; runs on NERSC)."""

from __future__ import annotations  # Required for Optional[Callable[...]] on Perlmutter 3.8

import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from blast_lib.iterative_loop.slurm_cancel import scancel_job_local
from blast_lib.iterative_loop.slurm_job_state import (
    fetch_sacct_job_state_local,
    slurm_state_is_terminal,
    slurm_state_ok_after_gpu_walltime,
)

from blast_lib.iterative_loop.ho_report_local import (
    NO_ELASTIC_CANDIDATE,
    history_mode_for_cycle_start,
    require_scored_trials_count,
    scored_trials_before_cycle,
)
from blast_lib.iterative_loop.blocked_property_improvement_watcher import (
    BlockedPropertyImprovementWatcher,
)
from blast_lib.iterative_loop.blocked_property_state import BlockedPropertyState
from blast_lib.iterative_loop.elastic_improvement_watcher import ElasticImprovementWatcher
from blast_lib.iterative_loop.range_core import apply_recenter_from_trial, run_range_update_local
from blast_lib.iterative_loop.recenter_trigger import RECENTER_IMPROVEMENT
from blast_lib.iterative_loop.region_provenance import (
    append_improvement_event,
    archive_region_report,
    prepare_fresh_active_report,
)
from blast_lib.agenticblast_submit import write_blast_root_input_txt
from blast_lib.iterative_loop.hierarchy_constants import (
    DECISION_ALL_PROPERTIES_PASSED,
    DECISION_NO_SWAPPABLE_PROPERTY,
    DECISION_SWITCH,
    DECISION_SWITCH_SKIPPED_MAX,
)
from blast_lib.iterative_loop.hierarchy_decision import HierarchyWindowDecision
from blast_lib.iterative_loop.hierarchy_provenance import (
    append_hierarchy_event,
    archive_hierarchy_epoch_report,
    archive_mcts_tree_if_present,
    prepare_fresh_active_report as prepare_fresh_hierarchy_report,
    reset_mcts_tree_files,
)
from blast_lib.iterative_loop.hierarchy_switch import apply_hierarchy_switch_local
from blast_lib.iterative_loop.hierarchy_window import HierarchyObservationWindow
from blast_lib.iterative_loop.hierarchy_pass_counts import normalize_hierarchy
from blast_lib.iterative_loop.selection_strategy import (
    STRATEGY_ELASTIC,
    STRATEGY_OVERALL,
    StrategyConfig,
    is_blocked_property_improvement_strategy,
    is_improvement_elastic_strategy,
    is_time_based_first_unpassed_hierarchy_strategy,
    load_strategy_config,
)
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
from blast_lib.iterative_loop.allocation_teardown import drain_interactive_allocation
from blast_lib.iterative_loop.hierarchy_constants import DEFAULT_MAX_CONSECUTIVE_FAILED_ALLOCATIONS
from blast_lib.iterative_loop.salloc_command import SallocSettings, build_interactive_runbop_shell
from blast_lib.iterative_loop.salloc_run_log import (
    persist_salloc_run_output,
    record_allocation_failure_snapshot,
)
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
    aborted: bool = False
    abort_reason: str | None = None  # "stop" | "improvement" | "hierarchy_switch" | None
    terminal_slurm_state: str | None = None


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
    max_consecutive_failed_allocations: int = DEFAULT_MAX_CONSECUTIVE_FAILED_ALLOCATIONS
    poll_slurm_job_state: PollSlurmJobState = fetch_sacct_job_state_local
    drain_interactive_allocation_fn: Callable[..., str | None] = drain_interactive_allocation


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
    try:
        before = scored_trials_before_cycle(rp, cycle=cycle)
    except FileNotFoundError as exc:
        wf.status = WorkflowStatus.FAILED
        wf.phase = WorkflowPhase.FAILED
        wf.error = str(exc)
        wf.status_message = str(exc)
        hooks.save_workflow(wf_path, wf)
        return False, wf

    mode = history_mode_for_cycle_start(rp, cycle=cycle)
    if mode:
        wf.history_mode = mode
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
    try:
        after = require_scored_trials_count(rp)
    except FileNotFoundError as exc:
        rec.range_status = "FAILED"
        rec.error = str(exc)
        wf.status = WorkflowStatus.FAILED
        wf.phase = WorkflowPhase.FAILED
        wf.error = str(exc)
        wf.status_message = str(exc)
        hooks.save_workflow(wf_path, wf)
        return False, wf
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
            "selection_strategy": range_result.selection_strategy,
            "selection_reason": range_result.selection_reason,
            "elastic_values_obj": range_result.elastic_values_obj,
        },
    )

    if not range_result.ok:
        if NO_ELASTIC_CANDIDATE in (range_result.message or ""):
            rec.range_status = "NO_ELASTIC_CANDIDATE"
            rec.error = range_result.message
            wf.status = WorkflowStatus.STOPPED
            wf.phase = WorkflowPhase.STOPPED
            wf.error = None
            wf.status_message = range_result.message
            hooks.save_workflow(wf_path, wf)
            return False, wf
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


def _apply_strategy_config_to_workflow(wf: Any, cfg: StrategyConfig) -> None:
    wf.selection_strategy = cfg.selection_strategy
    wf.recenter_trigger = cfg.recenter_trigger
    wf.improvement_tolerance = cfg.improvement_tolerance
    if wf.incumbent_elastic_obj is None and cfg.incumbent_elastic_obj is not None:
        wf.incumbent_elastic_obj = cfg.incumbent_elastic_obj
    if wf.max_regions is None:
        wf.max_regions = cfg.max_regions
    if wf.max_total_runtime_sec is None and cfg.max_total_runtime_sec is not None:
        wf.max_total_runtime_sec = cfg.max_total_runtime_sec


def _runtime_budget_exceeded(wf: Any) -> bool:
    limit = wf.max_total_runtime_sec
    if not limit or wf.workflow_started_monotonic is None:
        return False
    return (time.monotonic() - wf.workflow_started_monotonic) >= float(limit)


def _apply_blocked_property_config_to_workflow(wf: Any, cfg: StrategyConfig) -> None:
    wf.orchestrator_strategy = cfg.orchestrator_strategy
    if not wf.active_hierarchy:
        wf.active_hierarchy = list(cfg.active_hierarchy)
    wf.improvement_tolerance = cfg.improvement_tolerance
    if wf.max_regions is None:
        wf.max_regions = cfg.max_regions
    if wf.max_total_runtime_sec is None and cfg.max_total_runtime_sec is not None:
        wf.max_total_runtime_sec = cfg.max_total_runtime_sec
    BlockedPropertyState.from_workflow(wf)  # normalize pass/reach dict keys


def _sync_blocked_property_to_workflow(
    wf: Any, state: BlockedPropertyState, watcher: BlockedPropertyImprovementWatcher
) -> None:
    state.apply_to_workflow(wf)
    wf.incumbent_property_obj = watcher.incumbent_property_obj


def _apply_hierarchy_config_to_workflow(wf: Any, cfg: StrategyConfig) -> None:
    wf.orchestrator_strategy = cfg.orchestrator_strategy
    if not wf.active_hierarchy:
        wf.active_hierarchy = list(cfg.active_hierarchy)
    if wf.observation_window_sec is None and cfg.observation_window_sec is not None:
        wf.observation_window_sec = cfg.observation_window_sec
    if wf.max_hierarchy_switches is None and cfg.max_hierarchy_switches is not None:
        wf.max_hierarchy_switches = cfg.max_hierarchy_switches
    if wf.max_consecutive_failed_allocations is None and cfg.max_consecutive_failed_allocations is not None:
        wf.max_consecutive_failed_allocations = cfg.max_consecutive_failed_allocations


def _effective_max_consecutive_failed_allocations(wf: Any, cfg: StrategyConfig, hooks: OrchestratorHooks) -> int:
    if wf.max_consecutive_failed_allocations is not None:
        return max(1, int(wf.max_consecutive_failed_allocations))
    if cfg.max_consecutive_failed_allocations is not None:
        return max(1, int(cfg.max_consecutive_failed_allocations))
    return max(1, int(hooks.max_consecutive_failed_allocations))


def _safe_scored_trial_count(hooks: OrchestratorHooks, report_path: Path) -> int:
    try:
        return int(hooks.count_trials(report_path))
    except FileNotFoundError:
        return 0


def _allocation_ended_acceptably(result: SallocRunResult) -> bool:
    if result.terminal_slurm_state and slurm_state_ok_after_gpu_walltime(result.terminal_slurm_state):
        return True
    if result.returncode == 0 and not result.aborted:
        return True
    if result.returncode == 0 and result.abort_reason == "hierarchy_switch":
        return True
    return False


def _persist_stream_shell_result(run_folder: Path, result: SallocRunResult) -> Path:
    return persist_salloc_run_output(
        run_folder,
        job_id=result.job_id,
        combined_output=result.combined_output,
        returncode=result.returncode,
        terminal_slurm_state=result.terminal_slurm_state,
        aborted=result.aborted,
        abort_reason=result.abort_reason,
    )


def _effective_max_hierarchy_switches(wf: Any, cfg: StrategyConfig) -> int | None:
    if wf.max_hierarchy_switches is not None:
        return int(wf.max_hierarchy_switches)
    if cfg.max_hierarchy_switches is not None:
        return int(cfg.max_hierarchy_switches)
    return None


def _record_window_event(
    run_folder: Path,
    wf: Any,
    window: HierarchyObservationWindow,
    decision: Any,
    *,
    gpu_job_id: str | None = None,
    switch_result: Any | None = None,
) -> None:
    payload: dict[str, Any] = {
        "observation_window_index": window.state.observation_window_index,
        "hierarchy_epoch": wf.hierarchy_epoch,
        "active_hierarchy": list(wf.active_hierarchy),
        "window_started_at": window.state.window_started_at_iso,
        "elapsed_seconds": window.elapsed_sec(),
        "scored_trials_in_window": decision.trials_in_window,
        "pass_counts": decision.pass_counts,
        "first_unpassed_property": decision.first_unpassed_property,
        "swapped_with_property": decision.swapped_with_property,
        "decision": decision.decision,
    }
    if decision.decision == DECISION_SWITCH and switch_result is not None:
        payload.update(
            {
                "previous_hierarchy": decision.active_hierarchy,
                "new_hierarchy": decision.target_hierarchy,
                "gpu_job_id": gpu_job_id,
                "main1_sha256_before": switch_result.main1_sha256_before,
                "main1_sha256_after": switch_result.main1_sha256_after,
                "model_json_sha256_before": switch_result.model_json_sha256,
                "model_json_sha256_after": switch_result.model_json_sha256,
                "mcts_restart_sha256_before": switch_result.mcts_restart_sha256,
                "mcts_restart_sha256_after": switch_result.mcts_restart_sha256,
            }
        )
    append_hierarchy_event(run_folder, payload)


def run_time_based_first_unpassed_hierarchy_orchestrator(
    wf_path: Path,
    wf: Any,
    *,
    step_b: str,
    hooks: OrchestratorHooks,
    cfg: StrategyConfig,
) -> int:
    """Observation-window pass counts → adjacent swap in main1.py; no model.json recenter."""
    run_folder = Path(wf.run_folder)
    rp = run_folder / "reports" / "ho.report"

    _apply_hierarchy_config_to_workflow(wf, cfg)
    if not wf.active_hierarchy:
        wf.active_hierarchy = list(cfg.active_hierarchy)
    if wf.observation_window_sec is None:
        return _fail(
            wf_path,
            wf,
            hooks,
            "time_based_first_unpassed_hierarchy requires observation_window in strategy.json",
        )

    if wf.workflow_started_monotonic is None:
        wf.workflow_started_monotonic = time.monotonic()
    if wf.window_started_monotonic is None:
        wf.window_started_monotonic = time.monotonic()

    try:
        write_blast_root_input_txt(wf.blast_root, [str(run_folder.resolve())])
    except OSError as exc:
        return _fail(wf_path, wf, hooks, f"Could not write blast_root input.txt: {exc}")

    wf.status = WorkflowStatus.RUNNING
    wf.phase = WorkflowPhase.AWAITING_SALLOC
    wf.status_message = (
        f"Hierarchy search epoch {wf.hierarchy_epoch} — "
        f"{' → '.join(normalize_hierarchy(wf.active_hierarchy))}"
    )
    hooks.save_workflow(wf_path, wf)

    window = HierarchyObservationWindow(
        rp,
        observation_window_sec=float(wf.observation_window_sec),
        active_hierarchy=list(wf.active_hierarchy),
        observation_window_index=int(wf.observation_window_index),
        scored_trial_start_index=int(wf.window_scored_trial_start),
        window_started_monotonic=wf.window_started_monotonic,
    )

    while True:
        if _stopped(wf_path, wf, hooks):
            return 0
        if _runtime_budget_exceeded(wf):
            wf.status = WorkflowStatus.COMPLETED
            wf.phase = WorkflowPhase.COMPLETED
            wf.status_message = "Workflow complete — max_total_runtime reached."
            wf.error = None
            hooks.save_workflow(wf_path, wf)
            return 0

        abort_state: dict[str, Any] = {"reason": None, "decision": None}

        def on_poll() -> None:
            if abort_state.get("reason"):
                return
            decision = window.evaluate_if_due()
            if decision is None:
                return
            if decision.decision == DECISION_SWITCH:
                max_sw = _effective_max_hierarchy_switches(wf, cfg)
                if max_sw is not None and int(wf.hierarchy_switch_count) >= max_sw:
                    skipped = HierarchyWindowDecision(
                        decision=DECISION_SWITCH_SKIPPED_MAX,
                        active_hierarchy=decision.active_hierarchy,
                        target_hierarchy=list(decision.active_hierarchy),
                        pass_counts=decision.pass_counts,
                        first_unpassed_property=decision.first_unpassed_property,
                        swapped_with_property=decision.swapped_with_property,
                        trials_in_window=decision.trials_in_window,
                    )
                    _record_window_event(run_folder, wf, window, skipped)
                    window.begin_next_window()
                    wf.observation_window_index = window.state.observation_window_index
                    wf.window_scored_trial_start = window.state.scored_trial_start_index
                    wf.window_started_monotonic = window.state.window_started_at_monotonic
                    hooks.save_workflow(wf_path, wf)
                    return
                abort_state["decision"] = decision
                abort_state["reason"] = "hierarchy_switch"
                return
            _record_window_event(run_folder, wf, window, decision)
            window.begin_next_window()
            wf.observation_window_index = window.state.observation_window_index
            wf.window_scored_trial_start = window.state.scored_trial_start_index
            wf.window_started_monotonic = window.state.window_started_at_monotonic
            hooks.save_workflow(wf_path, wf)

        def should_abort() -> bool:
            if abort_state.get("reason") == "hierarchy_switch":
                return True
            if _stopped(wf_path, wf, hooks):
                abort_state["reason"] = "stop"
                return True
            return False

        settings = salloc_settings_from_workflow(wf)
        shell_cmd = build_interactive_runbop_shell(settings, step_b=step_b)
        child_env = clear_inherited_slurm_env(hooks.env)
        wf.phase = WorkflowPhase.RUNNING_GPU
        wf.status_message = (
            f"Hierarchy epoch {wf.hierarchy_epoch}: awaiting interactive GPU "
            f"(window {window.state.observation_window_index})…"
        )
        hooks.save_workflow(wf_path, wf)

        def _on_salloc_granted(job_id: str) -> None:
            live = hooks.load_workflow(wf_path)
            live.current_interactive_job_id = job_id
            live.phase = WorkflowPhase.RUNNING_GPU
            live.status_message = (
                f"Hierarchy epoch {live.hierarchy_epoch}: allocation {job_id} running RunBOP…"
            )
            hooks.save_workflow(wf_path, live)

        trials_before = _safe_scored_trial_count(hooks, rp)

        result = stream_shell_run(
            shell_cmd,
            child_env,
            _on_salloc_granted,
            should_abort=should_abort,
            on_poll=on_poll,
            abort_state=abort_state,
            poll_slurm_job_state=hooks.poll_slurm_job_state,
        )

        log_path = _persist_stream_shell_result(run_folder, result)

        wf = hooks.load_workflow(wf_path)
        wf.current_interactive_job_id = None

        if _stopped(wf_path, wf, hooks):
            return 0

        if result.abort_reason == "hierarchy_switch" or abort_state.get("reason") == "hierarchy_switch":
            decision = abort_state.get("decision")
            if decision is None:
                return _fail(wf_path, wf, hooks, "Hierarchy switch abort without decision.")

            terminal_state = hooks.drain_interactive_allocation_fn(
                result.job_id,
                poll_fn=hooks.poll_slurm_job_state,
                sleep_fn=hooks.sleep,
                request_cancel=True,
            )
            if result.job_id:
                final_state = terminal_state or hooks.poll_slurm_job_state(str(result.job_id))
                if not final_state or not slurm_state_is_terminal(final_state):
                    return _fail(
                        wf_path,
                        wf,
                        hooks,
                        f"Hierarchy switch: interactive job {result.job_id} did not reach terminal state "
                        f"(last state {final_state!r}).",
                    )
                terminal_state = final_state

            switch_result = apply_hierarchy_switch_local(run_folder, decision)
            if not switch_result.ok:
                return _fail(wf_path, wf, hooks, switch_result.message)

            archived_trees = archive_mcts_tree_if_present(run_folder, epoch=int(wf.hierarchy_epoch))
            reset_mcts_tree_files(run_folder)

            metadata = {
                "decision": DECISION_SWITCH,
                "previous_hierarchy": decision.active_hierarchy,
                "new_hierarchy": switch_result.target_hierarchy,
                "pass_counts": decision.pass_counts,
                "first_unpassed_property": decision.first_unpassed_property,
                "swapped_with_property": decision.swapped_with_property,
                "gpu_job_id": result.job_id,
                "archived_mcts_files": archived_trees,
                "allocation_log": log_path.as_posix(),
                "allocation_terminal_slurm_state": terminal_state or result.terminal_slurm_state,
            }
            archive_hierarchy_epoch_report(run_folder, epoch=int(wf.hierarchy_epoch), metadata=metadata)
            prepare_fresh_hierarchy_report(run_folder)

            _record_window_event(
                run_folder,
                wf,
                window,
                decision,
                gpu_job_id=result.job_id,
                switch_result=switch_result,
            )

            wf.active_hierarchy = list(switch_result.target_hierarchy)
            wf.hierarchy_epoch = int(wf.hierarchy_epoch) + 1
            wf.hierarchy_switch_count = int(wf.hierarchy_switch_count) + 1
            wf.consecutive_failed_allocations = 0
            wf.last_allocation_failure_summary = None
            window.active_hierarchy = list(wf.active_hierarchy)
            window.begin_next_window()
            wf.observation_window_index = window.state.observation_window_index
            wf.window_scored_trial_start = window.state.scored_trial_start_index
            wf.window_started_monotonic = window.state.window_started_at_monotonic
            wf.status_message = (
                f"Hierarchy switch → {' → '.join(wf.active_hierarchy)} (epoch {wf.hierarchy_epoch})"
            )
            hooks.save_workflow(wf_path, wf)
            continue

        trials_after = _safe_scored_trial_count(hooks, rp)
        productive = trials_after > trials_before
        acceptable = _allocation_ended_acceptably(result)

        if productive or acceptable:
            wf.consecutive_failed_allocations = 0
            wf.last_allocation_failure_summary = None
            wf.phase = WorkflowPhase.AWAITING_SALLOC
            wf.status_message = (
                f"Hierarchy epoch {wf.hierarchy_epoch}: allocation ended; requesting another GPU…"
            )
            hooks.save_workflow(wf_path, wf)
            continue

        record_allocation_failure_snapshot(
            run_folder,
            job_id=result.job_id,
            returncode=result.returncode,
            terminal_slurm_state=result.terminal_slurm_state,
            log_path=log_path,
            combined_output=result.combined_output,
        )
        wf.consecutive_failed_allocations = int(wf.consecutive_failed_allocations or 0) + 1
        wf.last_allocation_job_id = result.job_id
        wf.last_allocation_returncode = result.returncode
        wf.last_allocation_slurm_state = result.terminal_slurm_state
        wf.last_allocation_log_path = log_path.as_posix()
        tail = (result.combined_output or "")[-500:]
        summary = (
            f"exit={result.returncode} slurm={result.terminal_slurm_state!r} "
            f"consecutive={wf.consecutive_failed_allocations}"
        )
        wf.last_allocation_failure_summary = summary
        max_fail = _effective_max_consecutive_failed_allocations(wf, cfg, hooks)
        msg = (
            f"Interactive allocation failed ({summary}). "
            f"See {log_path.name}. {tail}"
        )
        if wf.consecutive_failed_allocations >= max_fail:
            return _fail(
                wf_path,
                wf,
                hooks,
                f"{max_fail} consecutive failed interactive allocations. {msg}",
            )
        wf.phase = WorkflowPhase.AWAITING_SALLOC
        wf.status_message = f"{msg} Retrying after {hooks.salloc_retry_sleep_sec}s…"
        hooks.save_workflow(wf_path, wf)
        hooks.sleep(hooks.salloc_retry_sleep_sec)
        continue


def run_improvement_orchestrator(
    wf_path: Path,
    wf: Any,
    *,
    step_b: str,
    hooks: OrchestratorHooks,
    cfg: StrategyConfig,
) -> int:
    """Strategy 3: elastic selection + improvement-triggered recenter + fresh regions."""
    run_folder = Path(wf.run_folder)
    rp = run_folder / "reports" / "ho.report"

    _apply_strategy_config_to_workflow(wf, cfg)
    if wf.incumbent_elastic_obj is None:
        return _fail(
            wf_path,
            wf,
            hooks,
            "improvement strategy requires incumbent_elastic_obj in strategy.json or workflow.json",
        )
    if wf.max_regions is None or wf.max_regions < 1:
        wf.max_regions = cfg.max_regions

    if wf.workflow_started_monotonic is None:
        wf.workflow_started_monotonic = time.monotonic()

    wf.status = WorkflowStatus.RUNNING
    wf.phase = WorkflowPhase.AWAITING_SALLOC
    wf.status_message = (
        f"Elastic improvement search — region {wf.region}/{wf.max_regions}, "
        f"incumbent elastic.values.obj={wf.incumbent_elastic_obj}"
    )
    hooks.save_workflow(wf_path, wf)

    tolerance = float(wf.improvement_tolerance or cfg.improvement_tolerance)

    while wf.region < int(wf.max_regions):
        if _stopped(wf_path, wf, hooks):
            return 0
        if _runtime_budget_exceeded(wf):
            wf.status = WorkflowStatus.COMPLETED
            wf.phase = WorkflowPhase.COMPLETED
            wf.status_message = "Workflow complete — max_total_runtime reached."
            wf.error = None
            hooks.save_workflow(wf_path, wf)
            return 0

        wf.region_started_at = datetime.now(timezone.utc).isoformat()
        wf.trials_since_region_start = 0
        hooks.save_workflow(wf_path, wf)

        watcher = ElasticImprovementWatcher(
            rp,
            incumbent_elastic_obj=float(wf.incumbent_elastic_obj),
            improvement_tolerance=tolerance,
        )

        while True:
            if _stopped(wf_path, wf, hooks):
                return 0
            if _runtime_budget_exceeded(wf):
                wf.status = WorkflowStatus.COMPLETED
                wf.phase = WorkflowPhase.COMPLETED
                wf.status_message = "Workflow complete — max_total_runtime reached."
                wf.error = None
                hooks.save_workflow(wf_path, wf)
                return 0

            abort_state: dict[str, Any] = {"reason": None, "trigger": None}

            def on_poll() -> None:
                if abort_state.get("reason"):
                    return
                trigger = watcher.poll()
                if trigger is not None:
                    abort_state["trigger"] = trigger
                    abort_state["reason"] = "improvement"

            def should_abort() -> bool:
                if abort_state.get("reason") == "improvement":
                    return True
                if _stopped(wf_path, wf, hooks):
                    abort_state["reason"] = "stop"
                    return True
                return False

            settings = salloc_settings_from_workflow(wf)
            shell_cmd = build_interactive_runbop_shell(settings, step_b=step_b)
            child_env = clear_inherited_slurm_env(hooks.env)
            wf.phase = WorkflowPhase.RUNNING_GPU
            wf.status_message = (
                f"Region {wf.region}: awaiting interactive GPU (incumbent {wf.incumbent_elastic_obj})…"
            )
            hooks.save_workflow(wf_path, wf)

            def _on_salloc_granted(job_id: str) -> None:
                live = hooks.load_workflow(wf_path)
                live.current_interactive_job_id = job_id
                live.phase = WorkflowPhase.RUNNING_GPU
                live.status_message = (
                    f"Region {live.region}: interactive allocation {job_id} running RunBOP…"
                )
                hooks.save_workflow(wf_path, live)

            result = stream_shell_run(
                shell_cmd,
                child_env,
                _on_salloc_granted,
                should_abort=should_abort,
                on_poll=on_poll,
                abort_state=abort_state,
            )

            wf = hooks.load_workflow(wf_path)
            wf.current_interactive_job_id = None

            if _stopped(wf_path, wf, hooks):
                return 0

            if result.abort_reason == "improvement" or abort_state.get("reason") == "improvement":
                trigger = abort_state.get("trigger") or watcher.last_trigger
                if trigger is None:
                    return _fail(wf_path, wf, hooks, "Improvement abort without trigger trial.")

                wf.phase = WorkflowPhase.RUNNING_RANGE
                wf.status_message = "Improvement detected — recentering…"
                hooks.save_workflow(wf_path, wf)

                range_result = apply_recenter_from_trial(
                    run_folder,
                    wf.blast_python,
                    trigger.trial,
                    selection_strategy=STRATEGY_ELASTIC,
                    selection_reason="NEW_ELASTIC_CHAMPION",
                )
                if not range_result.ok:
                    return _fail(wf_path, wf, hooks, range_result.message)

                prev_incumbent = wf.incumbent_elastic_obj
                metadata = {
                    "selection_strategy": STRATEGY_ELASTIC,
                    "recenter_trigger": RECENTER_IMPROVEMENT,
                    "incumbent_elastic_obj_before": prev_incumbent,
                    "candidate_elastic_obj": trigger.candidate_elastic_obj,
                    "trigger_iteration": trigger.iteration,
                    "trigger_reason": "improvement",
                    "gpu_job_id": result.job_id,
                    "improvement_tolerance": tolerance,
                }
                archive_region_report(run_folder, region=int(wf.region), metadata=metadata)
                append_improvement_event(run_folder, metadata)
                prepare_fresh_active_report(run_folder)

                wf.incumbent_elastic_obj = trigger.candidate_elastic_obj
                wf.last_trigger_reason = "improvement"
                wf.last_trigger_iteration = trigger.iteration
                wf.region += 1
                wf.status_message = (
                    f"Recentered after elastic improvement → incumbent {wf.incumbent_elastic_obj} "
                    f"(region {wf.region})"
                )
                hooks.save_workflow(wf_path, wf)

                if wf.region >= int(wf.max_regions):
                    wf.status = WorkflowStatus.COMPLETED
                    wf.phase = WorkflowPhase.COMPLETED
                    wf.error = None
                    wf.status_message = f"Workflow complete — max_regions ({wf.max_regions}) reached."
                    hooks.save_workflow(wf_path, wf)
                    return 0
                break

            wf.phase = WorkflowPhase.AWAITING_SALLOC
            wf.status_message = (
                f"Region {wf.region}: allocation ended without improvement; requesting another GPU…"
            )
            hooks.save_workflow(wf_path, wf)
            continue

    wf.status = WorkflowStatus.COMPLETED
    wf.phase = WorkflowPhase.COMPLETED
    wf.status_message = f"Workflow complete — max_regions ({wf.max_regions}) reached."
    hooks.save_workflow(wf_path, wf)
    return 0


def run_blocked_property_improvement_orchestrator(
    wf_path: Path,
    wf: Any,
    *,
    step_b: str,
    hooks: OrchestratorHooks,
    cfg: StrategyConfig,
) -> int:
    """Generalized Strategy 3: blocked-property metric improvement + full-vector recenter."""
    run_folder = Path(wf.run_folder)
    rp = run_folder / "reports" / "ho.report"

    _apply_blocked_property_config_to_workflow(wf, cfg)
    if wf.max_regions is None or wf.max_regions < 1:
        wf.max_regions = cfg.max_regions

    if wf.workflow_started_monotonic is None:
        wf.workflow_started_monotonic = time.monotonic()

    state = BlockedPropertyState.from_workflow(wf)
    state.discover_target_if_needed()
    wf.status = WorkflowStatus.RUNNING
    wf.phase = WorkflowPhase.AWAITING_SALLOC
    target_msg = wf.target_property or "discovering blocked property"
    wf.status_message = (
        f"Blocked-property improvement — region {wf.region}/{wf.max_regions}, target={target_msg}"
    )
    hooks.save_workflow(wf_path, wf)

    tolerance = float(wf.improvement_tolerance or cfg.improvement_tolerance)

    while wf.region < int(wf.max_regions):
        if _stopped(wf_path, wf, hooks):
            return 0
        if _runtime_budget_exceeded(wf):
            wf.status = WorkflowStatus.COMPLETED
            wf.phase = WorkflowPhase.COMPLETED
            wf.status_message = "Workflow complete — max_total_runtime reached."
            wf.error = None
            hooks.save_workflow(wf_path, wf)
            return 0

        state = BlockedPropertyState.from_workflow(wf)
        state.discover_target_if_needed()
        if state.all_passed():
            wf.status = WorkflowStatus.COMPLETED
            wf.phase = WorkflowPhase.COMPLETED
            wf.status_message = "All hierarchy properties passed — objective satisfied."
            wf.error = None
            state.apply_to_workflow(wf)
            hooks.save_workflow(wf_path, wf)
            return 0

        wf.region_started_at = datetime.now(timezone.utc).isoformat()
        wf.trials_since_region_start = 0
        hooks.save_workflow(wf_path, wf)

        watcher = BlockedPropertyImprovementWatcher(
            rp,
            state=state,
            incumbent_property_obj=wf.incumbent_property_obj,
            improvement_tolerance=tolerance,
        )

        while True:
            if _stopped(wf_path, wf, hooks):
                return 0
            if _runtime_budget_exceeded(wf):
                wf.status = WorkflowStatus.COMPLETED
                wf.phase = WorkflowPhase.COMPLETED
                wf.status_message = "Workflow complete — max_total_runtime reached."
                wf.error = None
                hooks.save_workflow(wf_path, wf)
                return 0

            abort_state: dict[str, Any] = {"reason": None, "trigger": None}

            def on_poll() -> None:
                if abort_state.get("reason"):
                    return
                trigger = watcher.poll()
                live = hooks.load_workflow(wf_path)
                _sync_blocked_property_to_workflow(live, watcher.state, watcher)
                if watcher.last_target_advanced is not None:
                    adv = watcher.last_target_advanced
                    append_improvement_event(
                        run_folder,
                        {
                            "event_type": "target_property_advanced",
                            "region": live.region,
                            "old_target_property": adv.old_target_property,
                            "new_target_property": adv.new_target_property,
                            "reason": adv.reason,
                            "trigger_iteration": adv.trial.get("iteration"),
                            "property_passed_ever": dict(watcher.state.property_passed_ever),
                        },
                    )
                    live.incumbent_property_obj = None
                    watcher.last_target_advanced = None
                    hooks.save_workflow(wf_path, live)
                if watcher.state.all_passed():
                    abort_state["reason"] = "all_passed"
                    return
                if trigger is not None:
                    abort_state["trigger"] = trigger
                    abort_state["reason"] = "improvement"

            def should_abort() -> bool:
                if abort_state.get("reason") in ("improvement", "all_passed"):
                    return True
                if _stopped(wf_path, wf, hooks):
                    abort_state["reason"] = "stop"
                    return True
                return False

            settings = salloc_settings_from_workflow(wf)
            shell_cmd = build_interactive_runbop_shell(settings, step_b=step_b)
            child_env = clear_inherited_slurm_env(hooks.env)
            wf = hooks.load_workflow(wf_path)
            target = wf.target_property or "discovery"
            wf.phase = WorkflowPhase.RUNNING_GPU
            wf.status_message = (
                f"Region {wf.region}: target {target} "
                f"(incumbent {wf.incumbent_property_obj})…"
            )
            hooks.save_workflow(wf_path, wf)

            def _on_salloc_granted(job_id: str) -> None:
                live = hooks.load_workflow(wf_path)
                live.current_interactive_job_id = job_id
                live.phase = WorkflowPhase.RUNNING_GPU
                live.status_message = (
                    f"Region {live.region}: allocation {job_id} running RunBOP "
                    f"(target {live.target_property or 'discovery'})…"
                )
                hooks.save_workflow(wf_path, live)

            result = stream_shell_run(
                shell_cmd,
                child_env,
                _on_salloc_granted,
                should_abort=should_abort,
                on_poll=on_poll,
                abort_state=abort_state,
            )

            wf = hooks.load_workflow(wf_path)
            wf.current_interactive_job_id = None
            _sync_blocked_property_to_workflow(wf, watcher.state, watcher)

            if _stopped(wf_path, wf, hooks):
                return 0

            if abort_state.get("reason") == "all_passed" or watcher.state.all_passed():
                wf.status = WorkflowStatus.COMPLETED
                wf.phase = WorkflowPhase.COMPLETED
                wf.status_message = "All hierarchy properties passed — objective satisfied."
                wf.error = None
                hooks.save_workflow(wf_path, wf)
                return 0

            if result.abort_reason == "improvement" or abort_state.get("reason") == "improvement":
                trigger = abort_state.get("trigger") or watcher.last_improvement
                if trigger is None:
                    return _fail(wf_path, wf, hooks, "Improvement abort without trigger trial.")

                wf.phase = WorkflowPhase.RUNNING_RANGE
                wf.status_message = f"Improvement on {trigger.target_property} — recentering…"
                hooks.save_workflow(wf_path, wf)

                selection_reason = (
                    f"blocked_property_improvement:{trigger.target_property}:"
                    f"{trigger.metric_name}"
                )
                range_result = apply_recenter_from_trial(
                    run_folder,
                    wf.blast_python,
                    trigger.trial,
                    selection_strategy=STRATEGY_OVERALL,
                    selection_reason=selection_reason,
                )
                if not range_result.ok:
                    return _fail(wf_path, wf, hooks, range_result.message)

                metadata = {
                    "event_type": "blocked_property_recenter",
                    "selection_strategy": STRATEGY_OVERALL,
                    "recenter_trigger": RECENTER_IMPROVEMENT,
                    "region": int(wf.region),
                    "target_property": trigger.target_property,
                    "metric_name": trigger.metric_name,
                    "incumbent_before": trigger.incumbent_before,
                    "candidate_property_metric": trigger.candidate_property_metric,
                    "trigger_iteration": trigger.iteration,
                    "trigger_reason": "improvement",
                    "gpu_job_id": result.job_id,
                    "improvement_tolerance": tolerance,
                    "property_passed_ever": dict(wf.property_passed_ever),
                }
                archive_region_report(run_folder, region=int(wf.region), metadata=metadata)
                append_improvement_event(run_folder, metadata)
                prepare_fresh_active_report(run_folder)

                wf.incumbent_property_obj = None
                wf.last_trigger_reason = "improvement"
                wf.last_trigger_iteration = trigger.iteration
                wf.region += 1
                wf.status_message = (
                    f"Recentered after {trigger.target_property} improvement "
                    f"(region {wf.region}, target still {wf.target_property})"
                )
                hooks.save_workflow(wf_path, wf)

                if wf.region >= int(wf.max_regions):
                    wf.status = WorkflowStatus.COMPLETED
                    wf.phase = WorkflowPhase.COMPLETED
                    wf.error = None
                    wf.status_message = f"Workflow complete — max_regions ({wf.max_regions}) reached."
                    hooks.save_workflow(wf_path, wf)
                    return 0
                break

            wf.phase = WorkflowPhase.AWAITING_SALLOC
            wf.status_message = (
                f"Region {wf.region}: allocation ended without improvement; requesting another GPU…"
            )
            hooks.save_workflow(wf_path, wf)
            continue

    wf.status = WorkflowStatus.COMPLETED
    wf.phase = WorkflowPhase.COMPLETED
    wf.status_message = f"Workflow complete — max_regions ({wf.max_regions}) reached."
    hooks.save_workflow(wf_path, wf)
    return 0


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

    run_folder = Path(wf.run_folder)
    cfg = load_strategy_config(run_folder)
    if is_time_based_first_unpassed_hierarchy_strategy(cfg):
        return run_time_based_first_unpassed_hierarchy_orchestrator(
            wf_path, wf, step_b=step_b, hooks=hooks, cfg=cfg
        )
    if is_blocked_property_improvement_strategy(cfg):
        return run_blocked_property_improvement_orchestrator(
            wf_path, wf, step_b=step_b, hooks=hooks, cfg=cfg
        )
    if is_improvement_elastic_strategy(cfg):
        return run_improvement_orchestrator(wf_path, wf, step_b=step_b, hooks=hooks, cfg=cfg)

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
    """Kill only the session/process group started by this orchestrator Popen."""
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


OnPollInterval = Optional[Callable[[], None]]


def stream_shell_run(
    cmd: str,
    env: dict[str, str],
    on_salloc_granted: OnSallocGranted = None,
    *,
    should_abort: ShouldAbort = None,
    on_poll: OnPollInterval = None,
    abort_state: dict[str, Any] | None = None,
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
    resolved_abort_reason: str | None = None
    while proc.poll() is None:
        active_job = _known_job_id()

        if on_poll:
            on_poll()

        if should_abort and should_abort():
            aborted = True
            if abort_state and abort_state.get("reason"):
                resolved_abort_reason = str(abort_state["reason"])
            else:
                resolved_abort_reason = "stop"
            if active_job:
                scancel_job_local(active_job)
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
        aborted=aborted,
        abort_reason=resolved_abort_reason,
        terminal_slurm_state=terminal_slurm_state,
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
        count_trials=lambda rp: require_scored_trials_count(rp),
        sleep=time.sleep,
        load_workflow=load_workflow,
        save_workflow=save_workflow,
        env=env if env is not None else base,
    )
