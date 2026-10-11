"""Unit tests for main1 checkpoint patching."""

from blast_lib.main1_checkpoints import (
    apply_checkpoint_limits,
    apply_checkpoint_percentages,
    parse_checkpoint_limits,
    parse_main1_checkpoints,
)

SAMPLE = '''
prop = 'lattice'
obj.checkpoint(
    [
        "values.maxAE% <= 5.0",
    ],
)
prop = 'ce'
obj.checkpoint(
    [
        "values.maxAE% <= 4.0",
    ],
)
'''


def test_parse_main1_checkpoints():
    parsed = parse_main1_checkpoints(SAMPLE)
    assert "lattice" in parsed
    assert parsed["lattice"] == ["values.maxAE% <= 5.0"]
    assert parsed["ce"] == ["values.maxAE% <= 4.0"]


def test_apply_checkpoint_percentages():
    updated, missing = apply_checkpoint_percentages(
        SAMPLE,
        {"lattice": 3.0, "ce": 10.0, "eos": 1.0},
    )
    assert "eos" not in missing
    assert "values.maxAE% <= 3" in updated or "values.maxAE% <= 3.0" in updated
    assert "values.maxAE% <= 10" in updated or "values.maxAE% <= 10.0" in updated


EOS_SAMPLE = '''
prop = 'eos'
_failed = geo.checkpoint(prop,**{"conditions": [
    "shape.obj <= 166", "shift.obj <= 28"
]})
'''


def test_parse_and_apply_eos_limits():
    parsed = parse_checkpoint_limits(EOS_SAMPLE)
    assert parsed["eos_shape_obj"] == 166.0
    assert parsed["eos_shift_obj"] == 28.0
    updated, missing = apply_checkpoint_limits(
        EOS_SAMPLE,
        {"eos_shape_obj": 150.0, "eos_shift_obj": 25.0},
    )
    assert not missing
    assert "shape.obj <= 150" in updated
    assert "shift.obj <= 25" in updated
