"""Submit Next Job — user instructs the agent what to run."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import streamlit as st

from blast_lib.config import load_config
from blast_lib.job_instructions import (
    JobInstruction,
    dry_run_command,
    load_instruction,
    plan_summary,
    save_instruction,
    submit_job,
)
from blast_lib.remote import ssh_ping
from blast_lib.run_catalog import list_catalog_paths, resolve_run_path
from blast_lib.user_session import get_session

st.title("Submit Next Job")
st.caption("Tell the agent how the next run should differ — human approves before sbatch")

config = load_config()
session = get_session()
ssh_ok, ssh_msg = ssh_ping(config)

paths = list_catalog_paths(config, session)
if not paths:
    st.warning("No run folders. Configure `run_folders` in config/ui.yaml or add paths on **Run Dashboard**.")
    st.stop()

labels = {p.split("/")[-1]: p for p in paths}
folder_label = st.selectbox("Run folder", list(labels.keys()))
run_path = labels[folder_label]

st.markdown("**Examples:**")
st.markdown(
    "- Tighten bounds ±10% around best set and restart MCTS\n"
    "- Use two polymorphs for cohesive energy only (hybrid main1.py)\n"
    "- Increase elastic checkpoint tolerance by 5%\n"
    "- Change property stage order or enable/disable a stage"
)

instructions = st.text_area(
    "Your instructions for the next job",
    height=140,
    placeholder="e.g. Seed from best elastic trial, tighten ±10%, restart MCTS in this folder",
)

bound_pct = st.slider("Default bound tightening (%) if you mention tighten/narrow", 5, 25, 10)
use_mcts = st.checkbox("Run MCTS search (recommended)", value=True)

if st.button("Preview plan"):
    if not instructions.strip():
        st.error("Enter instructions first.")
    else:
        record = JobInstruction(
            run_folder_path=run_path,
            instructions=instructions.strip(),
            bound_tighten_pct=float(bound_pct),
            use_mcts=use_mcts,
        )
        save_instruction(record)
        st.subheader("Plan preview")
        st.code(plan_summary(record), language=None)
        st.info(
            "Apply main1.py / model.json edits on Perlmutter login node per instructions above, "
            "then confirm submit below."
        )

pending = load_instruction()
if pending:
    with st.expander("Last saved instruction", expanded=True):
        st.code(plan_summary(pending), language=None)

st.divider()
st.subheader("Submit to Perlmutter")

if not ssh_ok:
    st.error(f"SSH unavailable: {ssh_msg}")
else:
    st.code(dry_run_command(config, run_path), language="bash")
    confirm = st.checkbox("I applied config changes on Perlmutter (or this is a straight restart)")
    if confirm and st.button("sbatch", type="primary"):
        ok, msg = submit_job(config, run_path)
        if ok:
            st.success(msg)
            if pending:
                pending.status = "submitted"
                save_instruction(pending)
        else:
            st.error(msg)

st.caption("For email notifications of agent findings, set `notify_email` in config/ui.yaml (future).")
