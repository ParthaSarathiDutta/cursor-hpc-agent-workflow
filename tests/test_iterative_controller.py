"""Controller state machine tests (mocked SSH/submit/range)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from blast_lib.config_types import UIConfig
from blast_lib.iterative_loop.controller import IterativeRunController
from blast_lib.iterative_loop.range_agent import RangeUpdateResult
from blast_lib.iterative_loop.state import Phase, begin_workflow, load_state, save_state
from blast_lib.slurm_monitor import SlurmJobStatus


@pytest.fixture
def loop_config(tmp_path: Path) -> UIConfig:
    cfg = UIConfig()
    cfg.iterative_loop_state_path = str(tmp_path / "iterative_loop.json")
    cfg.blast_root = "/fake/blast"
    return cfg


class MockSubmit:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def submit(self, run_folder: str, walltime: str) -> str:
        self.calls.append((run_folder, walltime))
        return f"job{len(self.calls)}"


class MockRange:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, run_folder: str, *, report_already_synced: bool = False) -> RangeUpdateResult:
        self.calls += 1
        return RangeUpdateResult(ok=True, message="ok", best_score=100.0, best_iteration=self.calls)


def _patch_sync_counts(counts: list[int]):
    """Return side_effect that yields successive scored trial counts."""
    it = iter(counts)

    def _count(_path: Path) -> int:
        return next(it)

    return _count


@patch("blast_lib.iterative_loop.controller.sync_and_report_path")
@patch("blast_lib.iterative_loop.controller.count_scored_trials")
@patch("blast_lib.iterative_loop.controller.query_job_status")
def test_three_cycles_three_submissions(
    mock_query: MagicMock,
    mock_count: MagicMock,
    mock_sync: MagicMock,
    loop_config: UIConfig,
):
    mock_sync.return_value = Path("/cache/ho.report")
    # Before each submit + after each job: 10,11, 11,12, 12,13
    mock_count.side_effect = [10, 11, 11, 12, 12, 13]
    mock_query.side_effect = [
        SlurmJobStatus("job1", active=True, queue_state="RUNNING"),
        SlurmJobStatus("job1", active=False, sacct_state="TIMEOUT"),
        SlurmJobStatus("job2", active=False, sacct_state="COMPLETED"),
        SlurmJobStatus("job3", active=False, sacct_state="TIMEOUT"),
    ]

    submit = MockSubmit()
    range_agent = MockRange()
    ctrl = IterativeRunController(loop_config, submit_agent=submit, range_agent=range_agent)

    begin_workflow(
        loop_config,
        run_folder="/fake/blast/ML-Tersoff-1_PE",
        walltime="00:10:00",
        total_cycles=3,
    )

    for _ in range(20):
        state = load_state(loop_config)
        if state.phase in (Phase.COMPLETED, Phase.FAILED):
            break
        ctrl.tick()

    state = load_state(loop_config)
    assert state.phase == Phase.COMPLETED
    assert len(submit.calls) == 3
    assert range_agent.calls == 3
    assert state.last_completed_cycle == 3


@patch("blast_lib.iterative_loop.controller.sync_and_report_path")
@patch("blast_lib.iterative_loop.controller.count_scored_trials")
@patch("blast_lib.iterative_loop.controller.query_job_status")
def test_no_new_trials_fails_without_range_update(
    mock_query: MagicMock,
    mock_count: MagicMock,
    mock_sync: MagicMock,
    loop_config: UIConfig,
):
    mock_sync.return_value = Path("/cache/ho.report")
    mock_count.side_effect = [5, 5]
    mock_query.return_value = SlurmJobStatus("job1", active=False, sacct_state="COMPLETED")

    submit = MockSubmit()
    range_agent = MockRange()
    ctrl = IterativeRunController(loop_config, submit_agent=submit, range_agent=range_agent)

    begin_workflow(loop_config, run_folder="/fake/f", walltime="00:10:00", total_cycles=2)
    ctrl.tick()  # submit
    ctrl.tick()  # wait -> fail

    state = load_state(loop_config)
    assert state.phase == Phase.FAILED
    assert range_agent.calls == 0
    assert len(submit.calls) == 1


@patch("blast_lib.iterative_loop.controller.sync_and_report_path")
@patch("blast_lib.iterative_loop.controller.count_scored_trials")
@patch("blast_lib.iterative_loop.controller.query_job_status")
def test_waiting_with_job_id_does_not_resubmit(
    mock_query: MagicMock,
    mock_count: MagicMock,
    mock_sync: MagicMock,
    loop_config: UIConfig,
):
    mock_query.return_value = SlurmJobStatus("job99", active=True, queue_state="PENDING")
    submit = MockSubmit()
    ctrl = IterativeRunController(loop_config, submit_agent=submit, range_agent=MockRange())

    state = begin_workflow(loop_config, run_folder="/fake/f", walltime="00:10:00", total_cycles=1)
    state.touch(active_job_id="job99", phase=Phase.WAITING_FOR_JOB, scored_trial_count_before=1)
    save_state(loop_config, state)

    ctrl.tick()
    assert len(submit.calls) == 0


@patch("blast_lib.iterative_loop.controller.sync_and_report_path")
@patch("blast_lib.iterative_loop.controller.count_scored_trials")
def test_failed_submit_does_not_advance_cycle(
    mock_count: MagicMock,
    mock_sync: MagicMock,
    loop_config: UIConfig,
):
    mock_sync.return_value = Path("/cache/ho.report")
    mock_count.return_value = 3

    submit = MockSubmit()
    submit.submit = MagicMock(side_effect=RuntimeError("sbatch failed"))  # type: ignore[method-assign]
    ctrl = IterativeRunController(loop_config, submit_agent=submit, range_agent=MockRange())

    begin_workflow(loop_config, run_folder="/fake/f", walltime="00:10:00", total_cycles=3)
    ctrl.tick()

    state = load_state(loop_config)
    assert state.phase == Phase.FAILED
    assert state.current_cycle == 1


@patch("blast_lib.iterative_loop.controller.sync_and_report_path")
@patch("blast_lib.iterative_loop.controller.count_scored_trials")
@patch("blast_lib.iterative_loop.controller.query_job_status")
def test_failed_range_update_does_not_start_next_job(
    mock_query: MagicMock,
    mock_count: MagicMock,
    mock_sync: MagicMock,
    loop_config: UIConfig,
):
    mock_sync.return_value = Path("/cache/ho.report")
    mock_count.side_effect = [1, 2]
    mock_query.return_value = SlurmJobStatus("job1", active=False)

    submit = MockSubmit()
    bad_range = MockRange()
    bad_range.run = MagicMock(return_value=RangeUpdateResult(ok=False, message="changemodel error"))  # type: ignore[method-assign]
    ctrl = IterativeRunController(loop_config, submit_agent=submit, range_agent=bad_range)

    begin_workflow(loop_config, run_folder="/fake/f", walltime="00:10:00", total_cycles=3)
    for _ in range(5):
        state = load_state(loop_config)
        if state.phase == Phase.FAILED:
            break
        ctrl.tick()

    state = load_state(loop_config)
    assert state.phase == Phase.FAILED
    assert len(submit.calls) == 1


def test_cycle_counter_persisted(loop_config: UIConfig):
    state = begin_workflow(loop_config, run_folder="/fake/f", walltime="01:00:00", total_cycles=5)
    assert state.current_cycle == 1
    reloaded = load_state(loop_config)
    assert reloaded.total_cycles == 5
    assert reloaded.walltime == "01:00:00"
