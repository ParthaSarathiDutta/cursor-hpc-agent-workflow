"""Walltime parsing and sacct elapsed lookup for strict cycle completion."""

from __future__ import annotations

import re
import subprocess

from blast_lib.config_types import UIConfig

# Allow sacct to report slightly less than walltime (startup/teardown).
DEFAULT_WALLTIME_SLACK_SEC = 5

_ELAPSED_RE = re.compile(
    r"^(?:(?P<days>\d+)-)?(?P<hours>\d{2}):(?P<mins>\d{2}):(?P<secs>\d{2})$"
)


def parse_walltime_seconds(walltime: str) -> int:
    """Parse Slurm-style HH:MM:SS (optional leading days as D-HH:MM:SS)."""
    text = walltime.strip()
    if not text:
        raise ValueError("empty walltime")
    if "-" in text:
        days_part, _time_part = text.split("-", 1)
        days = int(days_part)
        rest = _time_part
    else:
        days = 0
        rest = text
    parts = rest.split(":")
    if len(parts) != 3:
        raise ValueError(f"invalid walltime {walltime!r}")
    h, m, s = (int(p) for p in parts)
    return days * 86400 + h * 3600 + m * 60 + s


def parse_sacct_elapsed_seconds(elapsed: str) -> int:
    """Parse sacct Elapsed field, e.g. 00:02:00 or 1-00:00:00."""
    text = elapsed.strip()
    if not text:
        raise ValueError("empty elapsed")
    m = _ELAPSED_RE.match(text)
    if not m:
        raise ValueError(f"unrecognized sacct Elapsed {elapsed!r}")
    days = int(m.group("days") or 0)
    h = int(m.group("hours"))
    mi = int(m.group("mins"))
    s = int(m.group("secs"))
    return days * 86400 + h * 3600 + mi * 60 + s


def fetch_job_elapsed_seconds_local(job_id: str) -> int | None:
    """Query sacct on the local node (Perlmutter batch/login). No SSH."""
    jid = job_id.strip()
    if not jid.isdigit():
        return None
    cmd = ["sacct", "-j", jid, "-X", "--format=Elapsed", "-P", "-n"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    out = (result.stdout or "").strip()
    if not out:
        return None
    try:
        return parse_sacct_elapsed_seconds(out.splitlines()[0].strip())
    except ValueError:
        return None


def fetch_job_elapsed_seconds(config: UIConfig, job_id: str) -> int | None:
    """Query Perlmutter sacct for the main job step (-X). Returns None if unavailable."""
    from blast_lib.remote import RemoteError, ssh_exec

    jid = job_id.strip()
    if not jid.isdigit():
        return None
    cmd = f"sacct -j {jid} -X --format=Elapsed -P -n 2>/dev/null | head -1"
    try:
        out = ssh_exec(config, cmd, timeout=30).strip()
    except RemoteError:
        return None
    if not out:
        return None
    try:
        return parse_sacct_elapsed_seconds(out.splitlines()[0].strip())
    except ValueError:
        return None


def allocation_met_walltime(
    elapsed_sec: int,
    walltime: str,
    *,
    slack_sec: int = DEFAULT_WALLTIME_SLACK_SEC,
) -> tuple[bool, int]:
    """True if elapsed >= requested walltime minus slack."""
    required = parse_walltime_seconds(walltime)
    minimum = max(0, required - slack_sec)
    return elapsed_sec >= minimum, required
