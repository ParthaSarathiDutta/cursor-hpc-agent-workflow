"""Perlmutter runtime deploy manifest (no SSH)."""

from blast_lib.iterative_loop.perlmutter_runtime_files import (
    PERLMUTTER_RUNTIME_REL_PATHS,
    iter_runtime_files,
)


def test_all_runtime_files_exist():
    paths = list(iter_runtime_files())
    assert len(paths) == len(PERLMUTTER_RUNTIME_REL_PATHS)
    allowed_remote = {"blast_lib/remote.py", "blast_lib/iterative_loop/remote_workflow.py"}
    for rel, _ in paths:
        if "remote" in rel:
            assert rel in allowed_remote


def test_runtime_modules_do_not_import_ssh_at_import(monkeypatch):
    """Perlmutter runtime must not require blast_lib.remote at import time."""
    import importlib
    import sys

    if "blast_lib.remote" in sys.modules:
        del sys.modules["blast_lib.remote"]

    def _block_remote_import(name, *args, **kwargs):
        if name == "blast_lib.remote" or name.startswith("blast_lib.remote."):
            raise ImportError(f"blocked {name}")
        return importlib.__import__(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "__import__", _block_remote_import)

    for mod in (
        "blast_lib.iterative_loop.slurm_timing",
        "blast_lib.iterative_loop.range_core",
        "blast_lib.iterative_loop.orchestrator_core",
        "blast_lib.iterative_loop.runbop_launch",
    ):
        importlib.import_module(mod)

    # Orchestrator entrypoint (script adds repo root on NERSC; here use package imports)
    importlib.import_module("scripts.agentic_loop_orchestrator")


def test_ho_report_local_import_chain():
    """Elastic selection pulls trial_details → main1_checkpoints → config (Perlmutter runtime)."""
    import importlib

    importlib.import_module("blast_lib.iterative_loop.ho_report_local")
    importlib.import_module("blast_lib.iterative_loop.orchestrator_core")


def test_orchestrator_script_import_chain():
    import importlib

    importlib.import_module("scripts.agentic_loop_orchestrator")
