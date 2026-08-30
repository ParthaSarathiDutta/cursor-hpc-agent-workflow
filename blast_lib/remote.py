"""SSH and rsync helpers for Perlmutter."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from blast_lib.config import REPO_ROOT, UIConfig


class RemoteError(RuntimeError):
    pass


def ssh_exec(config: UIConfig, remote_cmd: str, timeout: int = 30) -> str:
    cmd = ["ssh", config.ssh_host, remote_cmd]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RemoteError(f"SSH timed out after {timeout}s") from exc
    if result.returncode != 0:
        raise RemoteError(result.stderr.strip() or result.stdout.strip() or "SSH failed")
    return result.stdout


def ssh_ping(config: UIConfig, timeout: int = 10) -> tuple[bool, str]:
    """Quick SSH connectivity check."""
    try:
        out = ssh_exec(config, "echo ok", timeout=timeout)
        return True, out.strip() or "ok"
    except RemoteError as exc:
        return False, str(exc)


def squeue_me(config: UIConfig) -> str:
    try:
        return ssh_exec(config, "squeue --me")
    except RemoteError as exc:
        return f"(Could not reach Perlmutter — {exc})"


def tail_log(config: UIConfig, job_id: str, lines: int = 40) -> str:
    cmd = (
        f"cd {config.blast_root} 2>/dev/null || cd $HOME; "
        f"tail -n {lines} logs/blast_{job_id}.out 2>/dev/null || "
        f"tail -n {lines} slurm-{job_id}.out 2>/dev/null || "
        f"echo 'No log found for job {job_id}'"
    )
    try:
        return ssh_exec(config, cmd, timeout=20)
    except RemoteError as exc:
        return str(exc)


def sbatch_dry_run(config: UIConfig, run_folder: str) -> str:
    script = (REPO_ROOT / config.slurm_script).resolve()
    return (
        f"ssh {config.ssh_host} "
        f"'cd {config.blast_root}/{run_folder} && sbatch {script}'"
    )


def sbatch_submit(config: UIConfig, run_folder: str) -> str:
    script_name = Path(config.slurm_script).name
    remote = f"cd {config.blast_root}/{run_folder} && sbatch {script_name}"
    return ssh_exec(config, remote, timeout=30)


def sync_run_folder(config: UIConfig, folder: str) -> tuple[Path, datetime]:
    src = f"{config.ssh_host}:{config.blast_root}/{folder}/reports/"
    dest = config.local_cache_path / folder / "reports"
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [
        "rsync", "-az", "--partial",
        src, str(dest) + "/",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RemoteError(result.stderr.strip() or "rsync failed")
    return dest.parent, datetime.now(timezone.utc)


def sync_all_runs(config: UIConfig) -> dict[str, str]:
    results: dict[str, str] = {}
    for folder in config.run_folders:
        try:
            sync_run_folder(config, folder)
            results[folder] = "ok"
        except (RemoteError, subprocess.TimeoutExpired) as exc:
            results[folder] = str(exc)
    return results
