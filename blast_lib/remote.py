"""SSH and rsync helpers for Perlmutter."""

from __future__ import annotations

import base64
import shlex
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from blast_lib.config import REPO_ROOT, UIConfig


class RemoteError(RuntimeError):
    pass


@dataclass
class SSHStreamResult:
    returncode: int
    log: str


def ssh_stream_command(
    config: UIConfig,
    remote_cmd: str,
    *,
    timeout_sec: int = 14_400,
    allocate_tty: bool = False,
) -> Iterator[str]:
    """
    Stream merged stdout/stderr from a long-running SSH command line-by-line.
    Raises RemoteError on timeout or launch failure.
    """
    ssh_args = ["ssh", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=20"]
    if allocate_tty:
        ssh_args.append("-t")
    ssh_args.extend([config.ssh_host, remote_cmd])
    try:
        proc = subprocess.Popen(
            ssh_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        raise RemoteError(f"Failed to start ssh: {exc}") from exc

    assert proc.stdout is not None
    start = time.monotonic()
    while True:
        if timeout_sec and (time.monotonic() - start) > timeout_sec:
            proc.kill()
            proc.wait(timeout=5)
            raise RemoteError(f"SSH stream timed out after {timeout_sec}s")
        line = proc.stdout.readline()
        if line:
            yield line
            continue
        if proc.poll() is not None:
            break
        time.sleep(0.05)

    # Drain remainder
    rest = proc.stdout.read()
    if rest:
        yield rest


def ssh_stream_run(
    config: UIConfig,
    remote_cmd: str,
    *,
    timeout_sec: int = 14_400,
    allocate_tty: bool = False,
) -> SSHStreamResult:
    """Collect full log from ssh_stream_command and return exit code."""
    lines: list[str] = []
    # Keepalive: this call blocks for the full interactive walltime (minutes+); without
    # this, a brief Wi-Fi/network hiccup on the client can silently drop the SSH session.
    ssh_args = ["ssh", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=20"]
    if allocate_tty:
        ssh_args.append("-t")
    ssh_args.extend([config.ssh_host, remote_cmd])
    try:
        proc = subprocess.Popen(
            ssh_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        raise RemoteError(f"Failed to start ssh: {exc}") from exc

    assert proc.stdout is not None
    start = time.monotonic()
    while True:
        if timeout_sec and (time.monotonic() - start) > timeout_sec:
            proc.kill()
            proc.wait(timeout=5)
            raise RemoteError(f"SSH stream timed out after {timeout_sec}s")
        line = proc.stdout.readline()
        if line:
            lines.append(line)
            continue
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    rest = proc.stdout.read()
    if rest:
        lines.append(rest)
    code = proc.wait(timeout=5)
    return SSHStreamResult(returncode=code, log="".join(lines))


def ssh_exec(config: UIConfig, remote_cmd: str, timeout: int = 30) -> str:
    cmd = ["ssh", config.ssh_host, remote_cmd]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RemoteError(f"SSH timed out after {timeout}s") from exc
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        if not err or err == "SSH failed":
            err = (
                "non-zero exit from ssh (try ./scripts/setup-sshproxy.sh if >24h since login)"
            )
        raise RemoteError(err)
    return result.stdout


def ssh_read_file(config: UIConfig, remote_path: str, timeout: int = 30) -> str:
    """Read a remote file over SSH (login node)."""
    cmd = f"cat {shlex.quote(remote_path)}"
    return ssh_exec(config, cmd, timeout=timeout)


def ssh_write_file(config: UIConfig, remote_path: str, content: str, timeout: int = 30) -> None:
    """Write a remote file over SSH via base64 decode (login node)."""
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    parent = str(Path(remote_path).parent)
    remote_cmd = (
        f"mkdir -p {shlex.quote(parent)} && "
        f"printf '%s' {shlex.quote(encoded)} | base64 -d > {shlex.quote(remote_path)}"
    )
    ssh_exec(config, remote_cmd, timeout=timeout)


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


def sync_run_at_path(config: UIConfig, run_folder_path: str) -> Path:
    """Sync reports and key files from a user-provided full run path."""
    from blast_lib.user_session import local_cache_dir

    remote_base = run_folder_path.rstrip("/")
    if not remote_base.startswith("/"):
        remote_base = f"{config.blast_root.rstrip('/')}/{remote_base}"

    dest = local_cache_dir(config, remote_base)
    dest.mkdir(parents=True, exist_ok=True)
    remote_host = f"{config.ssh_host}:{remote_base}"

    specs = [
        ("reports/", dest / "reports", True),
        ("settings.json", dest / "settings.json", False),
        ("model.json", dest / "model.json", False),
        ("main1.py", dest / "main1.py", False),
        ("mcts_restart.tersoff", dest / "mcts_restart.tersoff", False),
    ]
    errors: list[str] = []
    for rel, local_path, is_dir in specs:
        src = f"{remote_host}/{rel}"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        dest_arg = str(local_path) + ("/" if is_dir else "")
        cmd = ["rsync", "-az", "--partial", src, dest_arg]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0 and "No such file" not in (result.stderr or ""):
            errors.append(f"{rel}: {result.stderr.strip() or 'rsync failed'}")
    if errors and not (dest / "reports" / "ho.report").is_file():
        raise RemoteError("; ".join(errors))
    return dest


def sync_run_folder(config: UIConfig, folder: str) -> tuple[Path, datetime]:
    """Legacy sync by folder name under blast_root."""
    path = f"{config.blast_root.rstrip('/')}/{folder}"
    dest = sync_run_at_path(config, path)
    return dest, datetime.now(timezone.utc)


def sbatch_submit_at_path(config: UIConfig, run_folder_path: str) -> str:
    script_name = Path(config.slurm_script).name
    remote = f"cd '{run_folder_path.rstrip('/')}' && sbatch {script_name}"
    return ssh_exec(config, remote, timeout=30)


def sbatch_dry_run_at_path(config: UIConfig, run_folder_path: str) -> str:
    script_name = Path(config.slurm_script).name
    return (
        f"ssh {config.ssh_host} "
        f"\"cd '{run_folder_path.rstrip('/')}' && sbatch {script_name}\""
    )


def sync_all_runs(config: UIConfig, run_paths: list[str] | None = None) -> dict[str, str]:
    from blast_lib.user_session import run_folder_name

    paths = run_paths or [
        f"{config.blast_root.rstrip('/')}/{folder}" for folder in config.run_folders
    ]
    results: dict[str, str] = {}
    for path in paths:
        label = run_folder_name(path)
        try:
            sync_run_at_path(config, path)
            results[label] = "ok"
        except (RemoteError, subprocess.TimeoutExpired) as exc:
            results[label] = str(exc)
    return results
