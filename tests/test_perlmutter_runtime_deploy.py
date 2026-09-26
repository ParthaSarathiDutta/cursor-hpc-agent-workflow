"""Perlmutter runtime deploy manifest (no SSH)."""

from blast_lib.iterative_loop.perlmutter_runtime_files import (
    PERLMUTTER_RUNTIME_REL_PATHS,
    iter_runtime_files,
)


def test_all_runtime_files_exist():
    paths = list(iter_runtime_files())
    assert len(paths) == len(PERLMUTTER_RUNTIME_REL_PATHS)
    for rel, _ in paths:
        assert "remote" not in rel or rel.endswith("remote_workflow.py")


def test_runtime_modules_do_not_import_ssh_at_import(monkeypatch):
    """GPU/Range import closure must not call ssh_exec on import."""
    import importlib
    import sys

    def boom(*args, **kwargs):
        raise AssertionError("ssh_exec must not run during Perlmutter job imports")

    monkeypatch.setitem(sys.modules, "blast_lib.remote", type(sys)("blast_lib.remote"))
    sys.modules["blast_lib.remote"].ssh_exec = boom  # type: ignore[attr-defined]

    importlib.import_module("blast_lib.iterative_loop.range_core")
    importlib.import_module("blast_lib.iterative_loop.ho_report_local")
