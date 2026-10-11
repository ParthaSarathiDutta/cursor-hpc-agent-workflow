"""input.txt trailing slash — required for parallel RunBOP paths."""

from __future__ import annotations

from pathlib import Path

from blast_lib.agenticblast_submit import format_input_txt_lines, write_blast_root_input_txt
from blast_lib.iterative_loop.runbop_launch import (
    RunBopLaunchSettings,
    format_parallel_runbop_command,
)


def test_format_input_txt_lines_requires_trailing_slash():
    body = format_input_txt_lines(["/global/cfs/cdirs/m4597/partha/AgenticBLAST/test_runs/foo"])
    line = body.strip()
    assert line.endswith("/")
    assert not line.endswith("//")
    assert "foo/" in body


def test_write_blast_root_input_txt(tmp_path: Path):
    root = tmp_path / "blast"
    root.mkdir()
    run = "/global/cfs/cdirs/m4597/partha/AgenticBLAST/test_runs/stageorder_smoke"
    path = write_blast_root_input_txt(str(root), [run])
    assert path.is_file()
    text = path.read_text().strip()
    assert text.endswith("/")
    assert text == run.rstrip("/") + "/"


def test_parallel_runbop_command_uses_slash_before_runbop():
    cmd = format_parallel_runbop_command(
        RunBopLaunchSettings(
            blast_root="/global/cfs/cdirs/m4597/partha/AgenticBLAST",
            blast_python="/usr/bin/python",
        )
    )
    assert "{}/RunBOP.py" in cmd
    assert "{}RunBOP.py" not in cmd.replace("{}/RunBOP.py", "")
