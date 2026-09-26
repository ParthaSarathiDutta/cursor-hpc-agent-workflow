from blast_lib.iterative_loop.slurm_timing import (
    allocation_met_walltime,
    parse_sacct_elapsed_seconds,
    parse_walltime_seconds,
)


def test_parse_walltime():
    assert parse_walltime_seconds("00:02:00") == 120
    assert parse_walltime_seconds("00:10:00") == 600


def test_parse_sacct_elapsed():
    assert parse_sacct_elapsed_seconds("00:00:08") == 8
    assert parse_sacct_elapsed_seconds("00:02:00") == 120


def test_allocation_met_walltime():
    ok, req = allocation_met_walltime(120, "00:02:00")
    assert req == 120
    assert ok is True
    ok_short, _ = allocation_met_walltime(8, "00:02:00")
    assert ok_short is False
