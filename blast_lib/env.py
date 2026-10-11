"""Load repo-root .env into os.environ (once per process)."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_LOADED = False


def load_repo_dotenv() -> None:
    """Load ``REPO_ROOT/.env`` without overriding variables already in the environment."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True

    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return

    try:
        from dotenv import load_dotenv
    except ImportError:
        _load_env_manual(env_path)
        return

    load_dotenv(env_path, override=False)


def _load_env_manual(env_path: Path) -> None:
    """Minimal .env parser when python-dotenv is not installed."""
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value
