"""One-shot SSH submit of full Slurm dependency chain on Perlmutter."""

from __future__ import annotations

import base64
import json
import shlex
import uuid
from dataclasses import dataclass

from blast_lib.agenticblast_submit import (
    clear_run_folder_tmp,
    normalize_run_path,
    write_input_txt,
)
from blast_lib.config_types import REPO_ROOT, UIConfig
from blast_lib.iterative_loop.batch_chain import (
    render_loop_gpu_slurm,
    render_loop_range_slurm,
    render_submit_chain_bash,
)
from blast_lib.iterative_loop.perlmutter_runtime_files import iter_runtime_files
from blast_lib.iterative_loop.remote_workflow import (
    CycleRecord,
    RemoteWorkflow,
    WorkflowStatus,
    is_active_status,
    workflow_json_path,
)
from blast_lib.remote import RemoteError, ssh_exec, ssh_write_file


@dataclass
class BatchChainSubmitResult:
    ok: bool
    message: str
    workflow_id: str | None = None


class BatchSubmitAgent:
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

    def _deploy_assets(self, *, walltime: str) -> None:
        cfg = self.config
        root = cfg.blast_root.rstrip("/")
        gpu_body = render_loop_gpu_slurm(cfg, batch_time=walltime)
        range_body = render_loop_range_slurm(cfg)
        ssh_write_file(cfg, f"{root}/{cfg.loop_gpu_slurm_remote_name}", gpu_body)
        ssh_write_file(cfg, f"{root}/{cfg.loop_range_slurm_remote_name}", range_body)
        for rel, local in iter_runtime_files():
            remote = f"{root}/{rel}"
            ssh_write_file(cfg, remote, local.read_text())
        ssh_exec(
            cfg,
            f"chmod +x {shlex.quote(root)}/scripts/agentic_loop_*.py",
            timeout=30,
        )

    def _write_remote_workflow(self, wf: RemoteWorkflow) -> None:
        path = workflow_json_path(wf.run_folder)
        payload = json.dumps(
            {
                "workflow_id": wf.workflow_id,
                "run_folder": wf.run_folder,
                "walltime": wf.walltime,
                "total_cycles": wf.total_cycles,
                "status": wf.status,
                "blast_root": wf.blast_root,
                "blast_python": wf.blast_python,
                "status_message": wf.status_message,
                "cycles": [{"cycle": c.cycle} for c in wf.cycles],
            },
            indent=2,
        )
        parent = path.parent.as_posix()
        dest = path.as_posix()
        tmp = dest + ".tmp"
        remote_cmd = (
            f"mkdir -p {shlex.quote(parent)} && "
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
    ) -> BatchChainSubmitResult:
        folder = normalize_run_path(self.config, run_folder)
        active = self._remote_workflow_active(folder)
        if active:
            return BatchChainSubmitResult(
                ok=False,
                message=f"Active workflow already exists on NERSC (status={active}). Stop or wait before starting a new one.",
            )

        wf_id = str(uuid.uuid4())
        wf = RemoteWorkflow(
            workflow_id=wf_id,
            run_folder=folder,
            walltime=walltime.strip(),
            total_cycles=int(total_cycles),
            status=WorkflowStatus.QUEUED,
            blast_root=self.config.blast_root.rstrip("/"),
            blast_python=self.config.blast_python,
            status_message="Submitting Slurm dependency chain…",
            cycles=[CycleRecord(cycle=i) for i in range(1, int(total_cycles) + 1)],
        )

        try:
            clear_run_folder_tmp(self.config, [folder])
            write_input_txt(self.config, [folder])
            self._deploy_assets(walltime=walltime.strip())
            self._write_remote_workflow(wf)

            chain_bash = render_submit_chain_bash(self.config, wf)
            script_path = f"{folder}/.agentic_loop/submit_chain.sh"
            ssh_write_file(self.config, script_path, chain_bash)
            ssh_exec(self.config, f"chmod +x {shlex.quote(script_path)}", timeout=20)
            out = ssh_exec(self.config, f"bash {shlex.quote(script_path)}", timeout=120)

            cli = f"{root}/scripts/agentic_loop_workflow_cli.py"
            mark_cmd = (
                f"{shlex.quote(self.config.blast_python)} {shlex.quote(cli)} mark-running "
                f"{shlex.quote(folder)} {shlex.quote('Slurm chain submitted; jobs running on NERSC.')}"
            )
            ssh_exec(self.config, f"cd {shlex.quote(root)} && {mark_cmd}", timeout=30)

        except RemoteError as exc:
            return BatchChainSubmitResult(ok=False, message=str(exc), workflow_id=wf_id)

        return BatchChainSubmitResult(
            ok=True,
            message=out.strip() or "Slurm dependency chain submitted.",
            workflow_id=wf_id,
        )


def cancel_remote_workflow(config: UIConfig, run_folder: str) -> None:
    path = workflow_json_path(run_folder)
    cmd = f"cat {shlex.quote(path.as_posix())} 2>/dev/null || true"
    raw = ssh_exec(config, cmd, timeout=30).strip()
    if not raw:
        return
    data = json.loads(raw)
    ids: list[str] = []
    for c in data.get("cycles") or []:
        for key in ("gpu_job_id", "range_job_id"):
            jid = c.get(key)
            if jid and str(jid).isdigit():
                ids.append(str(jid))
    for jid in dict.fromkeys(ids):
        ssh_exec(config, f"scancel {jid} 2>/dev/null || true", timeout=15)
    data["status"] = WorkflowStatus.STOPPED
    data["status_message"] = "Stopped by user (pending/running Slurm jobs cancelled)."
    data["error"] = None
    payload = base64.b64encode(json.dumps(data, indent=2).encode()).decode()
    parent = path.parent.as_posix()
    ssh_exec(
        config,
        f"mkdir -p {shlex.quote(parent)} && "
        f"printf '%s' {shlex.quote(payload)} | base64 -d > {shlex.quote(path.as_posix() + '.tmp')} && "
        f"mv {shlex.quote(path.as_posix() + '.tmp')} {shlex.quote(path.as_posix())}",
        timeout=30,
    )
