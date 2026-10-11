"""Slurm environment cleanup before nested salloc from cron/scrontab jobs."""

from __future__ import annotations


def slurm_env_keys(env: dict[str, str]) -> list[str]:
    return [k for k in env if k.startswith("SLURM_")]


def clear_inherited_slurm_env(env: dict[str, str]) -> dict[str, str]:
    """Return a copy of env with SLURM_* removed (NERSC scrontab/cron guidance)."""
    return {k: v for k, v in env.items() if not k.startswith("SLURM_")}
