"""Minimal main1.py template for hierarchy swap tests (not executed)."""


def objective(params):
    earlyexit = True
    prop = "lattice"
    _lattice_body = "lattice_stage"
    prop = "ce"
    _ce_body = "ce_stage"
    prop = "eos"
    _eos_body = "eos_stage"
    # prop = 'elastic'
    # _dead_elastic = 'must_not_move'
    prop = "phonon"
    _phonon_body = "phonon_stage"
    prop = "elastic"
    _elastic_body = "elastic_stage"
    return _elastic_body
