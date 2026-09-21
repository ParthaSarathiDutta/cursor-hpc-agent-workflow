"""Unit tests for model.json and mcts_restart helpers."""

from blast_lib.model_json_ops import (
    merge_search_bounds,
    parse_mcts_restart_line,
    tighten_bounds_around_vector,
)

SAMPLE_MODEL = {
    "model": {
        "SbSb": {
            "m": "1",
            "gamma": "[0.1, 0.9]  %.6f",
            "c": "[1.0, 2.0]  %.6f",
            "d": "[0.5, 1.5]  %.6f",
        }
    }
}


def test_parse_mcts_restart_line_uses_last_n_params():
    line = "Sb Sb Sb 1 0.5 1.5 1.0"
    assert parse_mcts_restart_line(line, searchable_count=3) == [0.5, 1.5, 1.0]


def test_tighten_bounds_around_vector():
    out = tighten_bounds_around_vector(SAMPLE_MODEL, [0.5, 1.5, 1.0], 10.0)
    block = out["model"]["SbSb"]
    assert "0.45" in block["gamma"] or "0.450" in block["gamma"]


def test_merge_search_bounds_widest():
    other = {
        "model": {
            "SbSb": {
                "m": "1",
                "gamma": "[0.0, 1.0]  %.6f",
                "c": "[2.0, 3.0]  %.6f",
                "d": "[0.5, 1.5]  %.6f",
            }
        }
    }
    merged = merge_search_bounds([SAMPLE_MODEL, other])
    block = merged["model"]["SbSb"]
    assert block["gamma"].startswith("[0.0, 1.0]")
    assert block["c"].startswith("[1.0, 3.0]")
