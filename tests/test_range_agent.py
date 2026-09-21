"""Tests for RangeAgent helpers (no SSH)."""

from blast_lib.changemodel_bounds import TERSEOFF_PARAM_COUNT
from blast_lib.iterative_loop.range_agent import (
    DEFAULT_SB_PREFIX,
    extract_tersoff_floats,
    format_mcts_restart_line,
    split_mcts_restart_line,
)


def test_extract_tersoff_from_input_line():
    line = (
        "Sb-Sb: 1.868217 4.106359 446023.317447 490.265438 -0.061380 "
        "1.710080 0.83519 0.502200 21.307044 3.448513 1.342943 3.421116 11456.303102"
    )
    vals = extract_tersoff_floats(line)
    assert len(vals) == TERSEOFF_PARAM_COUNT
    assert vals[4] == -0.061380


def test_mcts_restart_preserves_sb_prefix():
    original = (
        "Sb Sb Sb 1       1.696936       4.052788  477518.973169 "
        "539.873418      -0.057293       1.603005       0.897216"
    )
    prefix, floats = split_mcts_restart_line(original + " 0.5 0.5 0.5 0.5 0.5 0.5")
    assert prefix == "Sb Sb Sb 1"
    assert len(floats) == TERSEOFF_PARAM_COUNT
    out = format_mcts_restart_line(prefix, floats)
    assert out.startswith("Sb Sb Sb 1")
    assert DEFAULT_SB_PREFIX in out
