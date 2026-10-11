"""Apply hierarchy switch to run folder (main1 only; invariants on model/restart)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from blast_lib.iterative_loop.hierarchy_decision import HierarchyWindowDecision
from blast_lib.iterative_loop.main1_hierarchy import (
    Main1HierarchyError,
    apply_adjacent_swap_to_main1,
    assert_target_order_in_source,
)


@dataclass(frozen=True)
class HierarchySwitchResult:
    ok: bool
    message: str
    target_hierarchy: list[str]
    main1_sha256_before: str
    main1_sha256_after: str
    model_json_sha256: str
    mcts_restart_sha256: str


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply_hierarchy_switch_local(
    run_folder: Path,
    decision: HierarchyWindowDecision,
) -> HierarchySwitchResult:
    run_folder = run_folder.resolve()
    main1_path = run_folder / "main1.py"
    model_path = run_folder / "model.json"
    restart_path = run_folder / "mcts_restart.tersoff"

    if decision.first_unpassed_property is None or decision.swapped_with_property is None:
        return HierarchySwitchResult(
            ok=False,
            message="Decision is not a SWITCH",
            target_hierarchy=decision.target_hierarchy,
            main1_sha256_before="",
            main1_sha256_after="",
            model_json_sha256="",
            mcts_restart_sha256="",
        )

    if not main1_path.is_file():
        return HierarchySwitchResult(
            ok=False,
            message=f"Missing {main1_path}",
            target_hierarchy=decision.target_hierarchy,
            main1_sha256_before="",
            main1_sha256_after="",
            model_json_sha256=_sha256_file(model_path) if model_path.is_file() else "",
            mcts_restart_sha256=_sha256_file(restart_path) if restart_path.is_file() else "",
        )

    model_before = _sha256_file(model_path) if model_path.is_file() else ""
    restart_before = _sha256_file(restart_path) if restart_path.is_file() else ""

    source = main1_path.read_text()
    main1_before = _sha256_text(source)

    try:
        updated, target = apply_adjacent_swap_to_main1(
            source,
            active_hierarchy=decision.active_hierarchy,
            first_unpassed=decision.first_unpassed_property,
        )
        assert_target_order_in_source(updated, target)
    except Main1HierarchyError as exc:
        return HierarchySwitchResult(
            ok=False,
            message=str(exc),
            target_hierarchy=decision.target_hierarchy,
            main1_sha256_before=main1_before,
            main1_sha256_after="",
            model_json_sha256=model_before,
            mcts_restart_sha256=restart_before,
        )

    main1_path.write_text(updated)
    main1_after = _sha256_text(updated)

    model_after = _sha256_file(model_path) if model_path.is_file() else ""
    restart_after = _sha256_file(restart_path) if restart_path.is_file() else ""

    if model_before != model_after:
        return HierarchySwitchResult(
            ok=False,
            message="model.json checksum changed during hierarchy switch (invariant violation)",
            target_hierarchy=target,
            main1_sha256_before=main1_before,
            main1_sha256_after=main1_after,
            model_json_sha256=model_after,
            mcts_restart_sha256=restart_after,
        )
    if restart_before != restart_after:
        return HierarchySwitchResult(
            ok=False,
            message="mcts_restart.tersoff checksum changed during hierarchy switch (invariant violation)",
            target_hierarchy=target,
            main1_sha256_before=main1_before,
            main1_sha256_after=main1_after,
            model_json_sha256=model_after,
            mcts_restart_sha256=restart_after,
        )

    return HierarchySwitchResult(
        ok=True,
        message="Hierarchy switch applied",
        target_hierarchy=target,
        main1_sha256_before=main1_before,
        main1_sha256_after=main1_after,
        model_json_sha256=model_after,
        mcts_restart_sha256=restart_after,
    )
