"""Local range update on filesystem (mocked sacct/changemodel)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from blast_lib.iterative_loop.range_core import run_range_update_local


@pytest.fixture
def mini_run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    reports = run / "reports"
    reports.mkdir(parents=True)
    # minimal ho.report lines parsed by parser — use fixture from tests if needed
    ho = reports / "ho.report"
    ho.write_text(
        "input Sb-Sb: 1 2 3 4 5 6 7 8 9 10 11 12 13\n"
        "# 100.0 | finalObj |\n"
        "input Sb-Sb: 1.1 2.2 3.3 4.4 5.5 6.6 7.7 8.8 9.9 10.1 11.2 12.3 13.4\n"
        "# 50.0 | finalObj |\n"
    )
    (run / "mcts_restart.tersoff").write_text(
        "Sb Sb Sb 1 1 2 3 4 5 6 7 8 9 10 11 12 13\n"
    )
    return run


@patch("blast_lib.iterative_loop.range_core.subprocess.run")
@patch("blast_lib.iterative_loop.range_core.fetch_job_elapsed_seconds_local", return_value=14400)
def test_range_success(mock_elapsed: MagicMock, mock_run: MagicMock, mini_run: Path):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
    result = run_range_update_local(
        mini_run,
        "python",
        scored_before=1,
        gpu_job_id="999",
        walltime="04:00:00",
    )
    assert result.ok
    assert result.best_score == 50.0


@patch("blast_lib.iterative_loop.range_core.fetch_job_elapsed_seconds_local", return_value=60)
def test_range_fails_short_walltime(_mock: MagicMock, mini_run: Path):
    result = run_range_update_local(
        mini_run,
        "python",
        scored_before=0,
        gpu_job_id="999",
        walltime="04:00:00",
    )
    assert not result.ok
    assert "too short" in result.message.lower()


@patch("blast_lib.iterative_loop.range_core.fetch_job_elapsed_seconds_local", return_value=14400)
def test_range_fails_no_trial_growth(_mock: MagicMock, mini_run: Path):
    result = run_range_update_local(
        mini_run,
        "python",
        scored_before=999,
        gpu_job_id="999",
        walltime="04:00:00",
    )
    assert not result.ok
    assert "No new scored trials" in result.message
