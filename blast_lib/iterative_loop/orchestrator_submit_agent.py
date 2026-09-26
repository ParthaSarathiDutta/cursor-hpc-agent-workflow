"""One-shot SSH: deploy runtime + sbatch cron orchestrator on Perlmutter."""

from __future__ import annotations

import base64
import json
import re
import shlex
import uuid
from dataclasses import dataclass
from blast_lib.agenticblast_submit import clear_run_folder_tmp, normalize_run_path, write_input_txt
from blast_lib.config_types import REPO_ROOT, UIConfig
from blast_lib.iterative_loop.orchestrator_core import estimate_orchestrator_cron_walltime
from blast_lib.iterative_loop.perlmutter_runtime_files import iter_runtime_files
from blast_lib.iterative_loop.remote_workflow import (
    CycleRecord,
    RemoteWorkflow,
    WorkflowPhase,
    WorkflowStatus,
    is_active_status,
    workflow_json_path,
)
from blast_lib.iterative_loop.slurm_cancel import (
    collect_orchestrator_workflow_cancel_ids,
    scancel_jobs_via_ssh,
)
from blast_lib.remote import RemoteError, ssh_exec, ssh_write_file

_SBATCH_PARSABLE_RE = re.compile(r"^(\d+)")


@dataclass
class OrchestratorSubmitResult:
    ok: bool
    message: str
    workflow_id: str | None = None
    orchestrator_job_id: str | None = None


def _parse_sbatch_parsable(out: str) -> str | None:
    line = (out or "").strip().splitlines()[0] if out else ""
    m = _SBATCH_PARSABLE_RE.match(line)
    return m.group(1) if m else None


def render_orchestrator_slurm(config: UIConfig, *, log_dir: str, walltime: str) -> str:
    template = (REPO_ROOT / "slurm" / "agentic_loop_orchestrator.slurm").read_text()
    return (
        template.replace("{{ORCHESTRATOR_ACCOUNT}}", config.orchestrator_cron_account)
        .replace("{{ORCHESTRATOR_WALLTIME}}", walltime)
        .replace("{{LOG_DIR}}", log_dir.rstrip("/"))
    )


def _gpu_account(config: UIConfig) -> str:
    acct = (config.gpu_account or "").strip()
    if acct and acct != "YOUR_GPU_ACCOUNT_g":
        return acct
    return config.submit_account


class OrchestratorSubmitAgent:
    def __init__(self, config: UIConfig) -> None:
        self.config = config

    def _remote_workflow_active(self, run_folder: str) -> str | None:
        path = workflow_json_path(run_folder)
        cmd = f"test -f {shlex.quote(str(path))} && cat {shlex.quote(str(path))} || echo '{{}}'"
        try:
            raw = ssh_exec(self.config, cmd, timeout=30).strip()
        except RemoteError:
            return None
        if not raw or raw == "{}":
            return None
        try:
            data = json.loads(raw)
            status = data.get("status", "")
            if is_active_status(status):
                return status
        except json.JSONDecodeError:
            return "INVALID"
        return None

    def _deploy_assets(self) -> None:
        cfg = self.config
        root = cfg.blast_root.rstrip("/")
        for rel, local in iter_runtime_files():
            ssh_write_file(cfg, f"{root}/{rel}", local.read_text())
        orch_slurm = render_orchestrator_slurm(
            cfg,
            log_dir=f"{root}/.agentic_loop/logs",
            walltime=cfg.orchestrator_cron_walltime,
        )
        ssh_write_file(cfg, f"{root}/{cfg.orchestrator_slurm_remote_name}", orch_slurm)
        ssh_exec(
            cfg,
            f"chmod +x {shlex.quote(root)}/scripts/agentic_loop_*.py",
            timeout=30,
        )

    def _write_remote_workflow(self, wf: RemoteWorkflow) -> None:
        from dataclasses import asdict

        path = workflow_json_path(wf.run_folder)
        payload = json.dumps(asdict(wf), indent=2)
        parent = path.parent.as_posix()
        dest = path.as_posix()
        tmp = dest + ".tmp"
        remote_cmd = (
            f"mkdir -p {shlex.quote(parent)} && "
            f"mkdir -p {shlex.quote(parent)}/logs && "
            f"printf '%s' {shlex.quote(base64.b64encode(payload.encode()).decode())} | "
            f"base64 -d > {shlex.quote(tmp)} && mv {shlex.quote(tmp)} {shlex.quote(dest)}"
        )
        ssh_exec(self.config, remote_cmd, timeout=60)

    def submit(
        self,
        run_folder: str,
        *,
        walltime: str,
        total_cycles: int,
    ) -> OrchestratorSubmitResult:
        folder = normalize_run_path(self.config, run_folder)
        active = self._remote_workflow_active(folder)
        if active:
            return OrchestratorSubmitResult(
                ok=False,
                message=(
                    f"Active workflow already exists on NERSC (status={active}). "
                    "Stop or wait before starting a new one."
                ),
            )

        cfg = self.config
        wf_id = str(uuid.uuid4())
        gpu_acct = _gpu_account(cfg)
        cron_wall = estimate_orchestrator_cron_walltime(
            total_cycles=int(total_cycles),
            cycle_walltime=walltime.strip(),
            margin_hours=cfg.orchestrator_cron_margin_hours,
        )
        wf = RemoteWorkflow(
            workflow_id=wf_id,
            run_folder=folder,
            walltime=walltime.strip(),
            total_cycles=int(total_cycles),
            status=WorkflowStatus.QUEUED,
            phase=WorkflowPhase.QUEUED,
            current_cycle=0,
            blast_root=cfg.blast_root.rstrip("/"),
            blast_python=cfg.blast_python,
            gpu_account=gpu_acct,
            salloc_account=gpu_acct,
            salloc_nodes=cfg.salloc_nodes,
            salloc_ntasks_per_node=cfg.salloc_ntasks_per_node,
            salloc_gpus_per_task=cfg.salloc_gpus_per_task,
            salloc_gpus=cfg.salloc_gpus,
            salloc_qos=cfg.salloc_qos,
            status_message="Submitting NERSC orchestrator (cron QOS)…",
            cycles=[CycleRecord(cycle=i) for i in range(1, int(total_cycles) + 1)],
        )

        root = cfg.blast_root.rstrip("/")
        log_dir = f"{folder}/.agentic_loop/logs"
        slurm_path = f"{root}/{cfg.orchestrator_slurm_remote_name}"

        try:
            clear_run_folder_tmp(cfg, [folder])
            write_input_txt(cfg, [folder])
            self._deploy_assets()
            self._write_remote_workflow(wf)

            orch_slurm_body = render_orchestrator_slurm(cfg, log_dir=log_dir, walltime=cron_wall)
            ssh_write_file(cfg, slurm_path, orch_slurm_body)

            export_cmd = (
                f"export RUN_FOLDER={shlex.quote(folder)} "
                f"BLAST_ROOT={shlex.quote(root)} "
                f"BLAST_PYTHON={shlex.quote(cfg.blast_python)}"
            )
            sbatch_cmd = (
                f"cd {shlex.quote(root)} && {export_cmd} && "
                f"sbatch --parsable {shlex.quote(slurm_path)}"
            )
            out = ssh_exec(cfg, sbatch_cmd, timeout=120)
            orch_id = _parse_sbatch_parsable(out)
            if not orch_id:
                return OrchestratorSubmitResult(
                    ok=False,
                    message=f"sbatch did not return a job id: {out!r}",
                    workflow_id=wf_id,
                )

            wf.orchestrator_job_id = orch_id
            wf.status = WorkflowStatus.RUNNING
            wf.phase = WorkflowPhase.AWAITING_SALLOC
            wf.current_cycle = 1
            wf.status_message = f"Orchestrator job {orch_id} running on NERSC."
            self._write_remote_workflow(wf)

        except RemoteError as exc:
            return OrchestratorSubmitResult(ok=False, message=str(exc), workflow_id=wf_id)

        return OrchestratorSubmitResult(
            ok=True,
            message=out.strip() or f"Orchestrator submitted (job {orch_id}).",
            workflow_id=wf_id,
            orchestrator_job_id=orch_id,
        )


def cancel_orchestrator_workflow(config: UIConfig, run_folder: str) -> None:
    """scancel only job ids recorded in this run's workflow.json; mark STOPPED."""
    path = workflow_json_path(run_folder)
    cmd = f"cat {shlex.quote(path.as_posix())} 2>/dev/null || true"
    raw = ssh_exec(config, cmd, timeout=30).strip()
    if not raw:
        return
    data = json.loads(raw)
    ids = collect_orchestrator_workflow_cancel_ids(data)

    def _ssh(command: str, timeout: float) -> str:
        return ssh_exec(config, command, timeout=timeout)

    scancel_jobs_via_ssh(_ssh, ids)
    data["status"] = WorkflowStatus.STOPPED
    data["phase"] = WorkflowPhase.STOPPED
    data["status_message"] = "Stopped by user (orchestrator and interactive jobs cancelled)."
    data["error"] = None
    data["current_interactive_job_id"] = None
    payload = base64.b64encode(json.dumps(data, indent=2).encode()).decode()
    parent = path.parent.as_posix()
    ssh_exec(
        config,
        f"mkdir -p {shlex.quote(parent)} && "
        f"printf '%s' {shlex.quote(payload)} | base64 -d > {shlex.quote(path.as_posix() + '.tmp')} && "
        f"mv {shlex.quote(path.as_posix() + '.tmp')} {shlex.quote(path.as_posix())}",
        timeout=30,
    )
