"""Create Run Folder — copy template, seed, model.json, main1 checkpoints."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import streamlit as st

from blast_lib.agenticblast_submit import list_blast_run_dirs
from blast_lib.config import load_config
from blast_lib.remote import ssh_ping
from blast_lib.main1_checkpoints import (
    load_main1_text,
    parse_checkpoint_limits,
    parse_maxae_percentages,
)
from blast_lib.run_folder_setup import (
    RunFolderSpec,
    apply_run_folder_setup,
    load_run_folder_spec,
    preview_run_folder_setup,
    save_run_folder_spec,
)

_FALLBACK_LIMITS = {
    "eos_shape_obj": 166.0,
    "eos_shift_obj": 28.0,
    "phonon_ceil_maxae": 30.2,
    "elastic_mae_pct": 30.0,
}


def _checkpoint_defaults_from_template(config, template_path: str) -> tuple[dict[str, float], dict[str, float]]:
    text = load_main1_text(config, template_path)
    if not text:
        return {"lattice": 3.0, "ce": 3.0}, dict(_FALLBACK_LIMITS)
    pct = parse_maxae_percentages(text) or {"lattice": 3.0, "ce": 3.0}
    limits = {**_FALLBACK_LIMITS, **parse_checkpoint_limits(text)}
    return pct, limits
from blast_lib.run_catalog import list_catalog_paths
from blast_lib.user_session import get_session

st.title("Create Run Folder")
st.caption("Copy a template on Perlmutter, set checkpoints, seed, and model.json bounds")

config = load_config()
session = get_session()
ssh_ok, ssh_msg = ssh_ping(config)

if not ssh_ok:
    st.error(f"SSH unavailable: {ssh_msg}")
    st.stop()

remote_dirs: list[str] = []
if st.button("Refresh folder list from Perlmutter"):
    st.session_state["create_remote_dirs"] = list_blast_run_dirs(config)
remote_dirs = st.session_state.get("create_remote_dirs") or list_blast_run_dirs(config)
catalog = list_catalog_paths(config, session)
options = remote_dirs or catalog

pending = load_run_folder_spec()

st.subheader("1. New folder")
new_name = st.text_input("New folder name", value=pending.new_folder_name if pending else "")
template = st.selectbox(
    "Copy from folder (template)",
    options=options,
    format_func=lambda p: p.split("/")[-1],
    index=0,
)
st.caption(
    "This folder is **copied** to create the new run (`main1.py`, scripts, `model.json`, "
    "`mcts_restart.tersoff`, etc.). For most new runs you only need this one folder."
)

if st.session_state.get("cp_tpl") != template:
    st.session_state["cp_tpl"] = template
    tpl_pct, tpl_lim = _checkpoint_defaults_from_template(config, template)
    st.session_state["cp_lattice"] = tpl_pct.get("lattice", 3.0)
    st.session_state["cp_ce"] = tpl_pct.get("ce", 3.0)
    for k, v in tpl_lim.items():
        st.session_state[f"cp_{k}"] = v

st.subheader("2. main1.py checkpoints")
st.caption(
    "PE folders use **maxAE%** for lattice/ce; **EOS** uses objective caps "
    "`shape.obj` and `shift.obj` (not %); phonon uses `ceil.maxAE%`; elastic uses `values.MAE%`. "
    "Defaults load from the template’s synced `main1.py`."
)
c1, c2, c3 = st.columns(3)
with c1:
    pct_lattice = st.number_input(
        "lattice — values.maxAE% ≤",
        min_value=0.1,
        max_value=100.0,
        step=0.5,
        key="cp_lattice",
    )
    pct_ce = st.number_input(
        "ce — values.maxAE% ≤",
        min_value=0.1,
        max_value=100.0,
        step=0.5,
        key="cp_ce",
    )
with c2:
    eos_shape = st.number_input(
        "eos — shape.obj ≤",
        min_value=1.0,
        max_value=5000.0,
        step=1.0,
        key="cp_eos_shape_obj",
        help="Energy–volume curve shape objective (all three PE folders use 166 in template).",
    )
    eos_shift = st.number_input(
        "eos — shift.obj ≤",
        min_value=1.0,
        max_value=500.0,
        step=1.0,
        key="cp_eos_shift_obj",
        help="EOS energy-shift objective (templates use 28).",
    )
with c3:
    phonon_ceil = st.number_input(
        "phonon — ceil.maxAE% ≤",
        min_value=0.1,
        max_value=100.0,
        step=0.5,
        key="cp_phonon_ceil_maxae",
    )
    elastic_mae = st.number_input(
        "elastic — values.MAE% ≤",
        min_value=0.1,
        max_value=100.0,
        step=0.5,
        key="cp_elastic_mae_pct",
    )

checkpoint_pct = {
    "lattice": float(pct_lattice),
    "ce": float(pct_ce),
}
checkpoint_limits = {
    "eos_shape_obj": float(eos_shape),
    "eos_shift_obj": float(eos_shift),
    "phonon_ceil_maxae": float(phonon_ceil),
    "elastic_mae_pct": float(elastic_mae),
}

st.subheader("3. Starting potential (mcts_restart.tersoff)")
seed_mode_label = st.radio(
    "How to set the starting potential",
    ["keep_template", "copy_restart_file", "from_ho_report_trial"],
    format_func=lambda x: {
        "keep_template": "Use file from copied folder (default)",
        "copy_restart_file": "Replace with mcts_restart.tersoff from another folder",
        "from_ho_report_trial": "Build from ho.report trial in another folder",
    }[x],
    horizontal=False,
)

seed_from: str | None = None
if seed_mode_label == "keep_template":
    st.caption(
        "No extra step — `mcts_restart.tersoff` stays whatever was in the folder you copied in section 1."
    )
else:
    seed_diff = st.checkbox(
        "Seed from a **different** folder than the copy source (advanced)",
        value=False,
        help="Leave unchecked to use the same folder as section 1 — equivalent to re-copying only the restart file.",
    )
    if seed_diff:
        seed_from = st.selectbox(
            "Folder for restart / ho.report",
            options=options,
            format_func=lambda p: p.split("/")[-1],
        )
        st.caption(
            "Example: copy **ML-Tersoff-1_PE_12** (section 1) but seed from best trial in **ML-Tersoff-1_PE**."
        )
    else:
        seed_from = template
        st.info(f"Using the same folder as section 1: **{template.split('/')[-1]}**")

if seed_mode_label == "from_ho_report_trial":
    seed_rank = st.number_input("Trial rank (1 = best score)", min_value=1, max_value=20, value=1)
else:
    seed_rank = 1

copy_tree = False
if seed_mode_label != "keep_template":
    copy_tree = st.checkbox(
        "Copy mctree.restart from seed folder (else start a fresh MCTS tree)",
        value=False,
    )

st.subheader("4. model.json ranges")
bounds_mode = st.radio(
    "Bounds mode",
    [
        "copy_template",
        "tighten_around_restart",
        "tighten_around_trial",
        "merge",
        "manual_json",
    ],
    format_func=lambda x: {
        "copy_template": "Keep template model.json",
        "tighten_around_restart": "±% around mcts_restart (after seed step)",
        "tighten_around_trial": "±% around ho.report trial",
        "merge": "Merge (widest) bounds from folders",
        "manual_json": "Paste JSON manually",
    }[x],
)
tighten_pct = st.slider("± percent for tighten modes", 5, 50, 10)
merge_folders = st.multiselect(
    "Folders to merge bounds from",
    options=options,
    format_func=lambda p: p.split("/")[-1],
    disabled=bounds_mode != "merge",
)
manual_json = st.text_area(
    "Manual model.json",
    height=120,
    disabled=bounds_mode != "manual_json",
    placeholder='{"model": { ... }}',
)
tighten_trial_folder = st.selectbox(
    "Trial source folder (tighten_around_trial)",
    options=options,
    format_func=lambda p: p.split("/")[-1],
    disabled=bounds_mode != "tighten_around_trial",
)

spec = RunFolderSpec(
    new_folder_name=new_name.strip(),
    template_path=template,
    checkpoint_pct=checkpoint_pct,
    checkpoint_limits=checkpoint_limits,
    seed_mode=seed_mode_label,  # type: ignore[arg-type]
    seed_from_folder=None if seed_mode_label == "keep_template" else seed_from,
    seed_rank=int(seed_rank),
    copy_mctree_restart=copy_tree,
    bounds_mode=bounds_mode,  # type: ignore[arg-type]
    bounds_source_folders=list(merge_folders),
    tighten_pct=float(tighten_pct),
    tighten_rank=int(seed_rank),
    tighten_source_folder=tighten_trial_folder if bounds_mode == "tighten_around_trial" else None,
    manual_model_json=manual_json if bounds_mode == "manual_json" and manual_json.strip() else None,
)

if st.button("Preview plan"):
    with st.spinner("Checking template on Perlmutter (one SSH round-trip if not synced locally)…"):
        try:
            st.code(preview_run_folder_setup(config, spec), language=None)
            save_run_folder_spec(spec)
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))

st.subheader("5. Apply on Perlmutter")
confirm = st.checkbox("I confirm creating and modifying this folder on Perlmutter")
if st.button("Apply create run folder", type="primary", disabled=not (confirm and new_name.strip())):
    try:
        result = apply_run_folder_setup(config, spec)
        st.success(f"Created {result.new_folder_path}")
        for msg in result.messages:
            st.write(f"- {msg}")
        save_run_folder_spec(spec)
        st.info("Add folder to config/ui.yaml run_folders and Sync on Run Dashboard.")
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))

st.caption("See docs/run-folder-setup.md. Agent Chat can preview/save spec — Apply only here.")
