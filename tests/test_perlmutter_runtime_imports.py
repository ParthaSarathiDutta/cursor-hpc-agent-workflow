"""Perlmutter cron orchestrator import chain (deploy manifest regression)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from blast_lib.config_types import REPO_ROOT
from blast_lib.iterative_loop.perlmutter_runtime_files import PERLMUTTER_RUNTIME_REL_PATHS

_REQUIRED_FOR_ELASTIC = {
    "blast_lib/config.py",
    "blast_lib/env.py",
    "blast_lib/remote.py",
    "blast_lib/user_session.py",
    "blast_lib/trial_details.py",
    "blast_lib/main1_checkpoints.py",
    "blast_lib/iterative_loop/selection_strategy.py",
}


def test_runtime_manifest_includes_elastic_dependencies():
    paths = set(PERLMUTTER_RUNTIME_REL_PATHS)
    missing = _REQUIRED_FOR_ELASTIC - paths
    assert not missing, f"PERLMUTTER_RUNTIME_REL_PATHS missing: {missing}"


def test_orchestrator_import_chain_in_isolated_pythonpath():
    """Same layout as NERSC: BLAST_ROOT on sys.path, no repo config/ui.yaml required."""
    code = """
import sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from blast_lib.iterative_loop import orchestrator_core  # noqa: F401
from blast_lib.iterative_loop.ho_report_local import (
    best_elastic_trial_from_report,
    select_trial_for_range,
)
from blast_lib.iterative_loop.selection_strategy import STRATEGY_ELASTIC, STRATEGY_OVERALL
assert STRATEGY_ELASTIC == "elastic"
"""
    proc = subprocess.run(
        [sys.executable, "-c", code, str(REPO_ROOT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
