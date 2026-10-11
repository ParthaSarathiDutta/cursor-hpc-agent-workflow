"""Autonomous iterative BLAST fitting loop (single run folder)."""

from __future__ import annotations

from typing import Any

__all__ = [
    "IterativeRunController",
    "IterativeLoopState",
    "Phase",
    "load_state",
    "save_state",
]


def __getattr__(name: str) -> Any:
    if name == "IterativeRunController":
        from blast_lib.iterative_loop.controller import IterativeRunController

        return IterativeRunController
    if name in ("IterativeLoopState", "Phase", "load_state", "save_state"):
        from blast_lib.iterative_loop import state as _state

        return getattr(_state, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
