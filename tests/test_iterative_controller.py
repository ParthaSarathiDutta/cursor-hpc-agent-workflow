"""Controller state machine tests (mocked SSH/submit/range)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from blast_lib.config_types import UIConfig
from blast_lib.iterative_loop.controller import IterativeRunController
from blast_lib.iterative_loop.range_agent import RangeUpdateResult
from blast_lib.iterative_loop.submit_agent import InteractiveSubmitResult
from blast_lib.iterative_loop.state import Phase, begin_workflow, load_state, save_state


@pytest.fixture
def loop_config(tmp_path: Path) -> UIConfig:
    cfg = UIConfig()
    cfg.iterative_loop_state_path = str(tmp_path / "iterative_loop.json")
    cfg.blast_root = "/fake/blast"
    return cfg


class MockSubmit:
    def __init__(self) -> None:
        self.prepare_calls: list[str] = []
        self.interactive_calls: list[tuple[str, str]] = []

    def prepare_input(self, run_folder: str) -> None:
        self.prepare_calls.append(run_folder)

    def run_interactive(self, run_folder: str, walltime: str) -> InteractiveSubmitResult:
        self.interactive_calls.append((run_folder, walltime))
        n = len(self.interactive_calls)
        return InteractiveSubmitResult(returncode=0, log=f"Granted job allocation {1000 + n}", allocation_job_id=str(1000 + n))


class MockRange:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, run_folder: str, *, report_already_synced: bool = False) -> RangeUpdateResult:
        self.calls += 1
        return RangeUpdateResult(ok=True, message="ok", best_score=100.0, best_iteration=self.calls)


def _run_full_cycle(ctrl: IterativeRunController, loop_config: UIConfig) -> None:
    """Submit prep tick → interactive finish → post-range ticks."""
    ctrl.tick()
    state = load_state(loop_config)
    assert state.phase == Phase.RUNNING_INTERACTIVE
    result = ctrl.submit_agent.run_interactive(state.run_folder, state.walltime)  # type: ignore[attr-defined]
    ctrl.finish_interactive_cycle(result)


@patch("blast_lib.iterative_loop.controller.sync_and_report_path")
@patch("blast_lib.iterative_loop.controller.count_scored_trials")
def test_three_cycles_three_interactive_launches(
    mock_count: MagicMock,
    mock_sync: MagicMock,
    loop_config: UIConfig,
):
    mock_sync.return_value = Path("/cache/ho.report")
    mock_count.side_effect = [10, 11, 11, 12, 12, 13]

    submit = MockSubmit()
    range_agent = MockRange()
    ctrl = IterativeRunController(loop_config, submit_agent=submit, range_agent=range_agent)

    begin_workflow(
        loop_config,
        run_folder="/fake/blast/ML-Tersoff-1_PE",
        walltime="00:10:00",
        total_cycles=3,
    )

    for _ in range(3):
        _run_full_cycle(ctrl, loop_config)

    state = load_state(loop_config)
    assert state.phase == Phase.COMPLETED
    assert len(submit.interactive_calls) == 3
    assert len(submit.prepare_calls) == 3
    assert range_agent.calls == 3
    assert state.last_completed_cycle == 3


@patch("blast_lib.iterative_loop.controller.sync_and_report_path")
@patch("blast_lib.iterative_loop.controller.count_scored_trials")
def test_no_new_trials_fails_without_range_update(
    mock_count: MagicMock,
    mock_sync: MagicMock,
    loop_config: UIConfig,
):
    mock_sync.return_value = Path("/cache/ho.report")
    mock_count.side_effect = [5, 5]

    submit = MockSubmit()
    range_agent = MockRange()
    ctrl = IterativeRunController(loop_config, submit_agent=submit, range_agent=range_agent)

    begin_workflow(loop_config, run_folder="/fake/f", walltime="00:10:00", total_cycles=2)
    ctrl.tick()
    result = submit.run_interactive("/fake/f", "00:10:00")
    ctrl.finish_interactive_cycle(result)

    state = load_state(loop_config)
    assert state.phase == Phase.FAILED
    assert range_agent.calls == 0
    assert len(submit.interactive_calls) == 1


@patch("blast_lib.iterative_loop.controller.sync_and_report_path")
@patch("blast_lib.iterative_loop.controller.count_scored_trials")
def test_stale_interactive_launch_fails_without_resubmit(
    mock_count: MagicMock,
    mock_sync: MagicMock,
    loop_config: UIConfig,
):
    submit = MockSubmit()
    ctrl = IterativeRunController(loop_config, submit_agent=submit, range_agent=MockRange())

    state = begin_workflow(loop_config, run_folder="/fake/f", walltime="00:10:00", total_cycles=1)
    state.touch(
        phase=Phase.RUNNING_INTERACTIVE,
        interactive_launch_started=True,
        scored_trial_count_before=1,
    )
    save_state(loop_config, state)

    ctrl.tick()
    state = load_state(loop_config)
    assert state.phase == Phase.FAILED
    assert len(submit.interactive_calls) == 0


@patch("blast_lib.iterative_loop.controller.sync_and_report_path")
@patch("blast_lib.iterative_loop.controller.count_scored_trials")
def test_prepare_failure_does_not_advance(
    mock_count: MagicMock,
    mock_sync: MagicMock,
    loop_config: UIConfig,
):
    mock_sync.return_value = Path("/cache/ho.report")
    mock_count.return_value = 3

    submit = MockSubmit()
    submit.prepare_input = MagicMock(side_effect=RuntimeError("write failed"))  # type: ignore[method-assign]
    ctrl = IterativeRunController(loop_config, submit_agent=submit, range_agent=MockRange())

    begin_workflow(loop_config, run_folder="/fake/f", walltime="00:10:00", total_cycles=3)
    ctrl.tick()

    state = load_state(loop_config)
    assert state.phase == Phase.FAILED
    assert state.current_cycle == 1


@patch("blast_lib.iterative_loop.controller.sync_and_report_path")
@patch("blast_lib.iterative_loop.controller.count_scored_trials")
def test_failed_range_update_does_not_start_next_cycle(
    mock_count: MagicMock,
    mock_sync: MagicMock,
    loop_config: UIConfig,
):
    mock_sync.return_value = Path("/cache/ho.report")
    mock_count.side_effect = [1, 2, 2, 3]

    submit = MockSubmit()
    bad_range = MockRange()
    bad_range.run = MagicMock(return_value=RangeUpdateResult(ok=False, message="changemodel error"))  # type: ignore[method-assign]
    ctrl = IterativeRunController(loop_config, submit_agent=submit, range_agent=bad_range)

    begin_workflow(loop_config, run_folder="/fake/f", walltime="00:10:00", total_cycles=3)
    _run_full_cycle(ctrl, loop_config)

    state = load_state(loop_config)
    assert state.phase == Phase.FAILED
    assert len(submit.interactive_calls) == 1


@patch("blast_lib.iterative_loop.controller.sync_and_report_path")
@patch("blast_lib.iterative_loop.controller.count_scored_trials")
def test_stop_requested_after_cycle_skips_next_interactive(
    mock_count: MagicMock,
    mock_sync: MagicMock,
    loop_config: UIConfig,
):
    mock_sync.return_value = Path("/cache/ho.report")
    mock_count.side_effect = [1, 2]

    submit = MockSubmit()
    ctrl = IterativeRunController(loop_config, submit_agent=submit, range_agent=MockRange())

    begin_workflow(loop_config, run_folder="/fake/f", walltime="00:10:00", total_cycles=3)
    _run_full_cycle(ctrl, loop_config)

    state = load_state(loop_config)
    state.touch(stop_requested=True)
    save_state(loop_config, state)

    ctrl.tick()
    state = load_state(loop_config)
    assert state.phase == Phase.STOPPED
    assert len(submit.interactive_calls) == 1


def test_cycle_counter_persisted(loop_config: UIConfig):
    state = begin_workflow(loop_config, run_folder="/fake/f", walltime="01:00:00", total_cycles=5)
    assert state.current_cycle == 1
    reloaded = load_state(loop_config)
    assert reloaded.total_cycles == 5
    assert reloaded.walltime == "01:00:00"
