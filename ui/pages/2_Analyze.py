"""Analyze — status, parameters, and predicted properties for user-connected runs."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import pandas as pd
import streamlit as st

from blast_lib.config import load_config
from blast_lib.remote import RemoteError, ssh_ping, sync_run_at_path
from blast_lib.run_io import load_run_outputs
from blast_lib.user_session import get_session, run_folder_name

st.title("Analyze")
st.caption("Outputs for runs you connected on **User Inputs**")

config = load_config()
ssh_ok, _ = ssh_ping(config)
session = get_session()

if not session.connected and not session.saved_runs:
    st.warning("No run connected yet. Go to **User Inputs**, enter your paths, and click **Connect**.")
    st.stop()

run_paths = session.saved_runs or ([session.run_folder_path] if session.run_folder_path else [])
run_path = st.selectbox(
    "Run folder to analyze",
    run_paths,
    index=run_paths.index(session.run_folder_path) if session.run_folder_path in run_paths else 0,
)

st.markdown(f"**Path:** `{run_path}`")

if st.button("Sync and analyze", disabled=not ssh_ok):
    with st.spinner("Syncing from Perlmutter..."):
        try:
            sync_run_at_path(config, run_path)
            st.success("Synced")
        except RemoteError as exc:
            st.warning(str(exc))

outputs = load_run_outputs(config, run_path, use_ssh=ssh_ok, sync_first=False)

st.subheader("Run status")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Run name", outputs.run_name)
c2.metric("Best finalObj", f"{outputs.best_score:,.0f}" if outputs.best_score else "—")
c3.metric("Deepest stage", outputs.deepest_stage)
c4.metric("Trials", outputs.trial_count)

if not outputs.report_exists:
    st.warning("No ho.report found — click **Sync and analyze** with SSH connected.")
else:
    st.success("All stages passed" if outputs.completed_all else f"Stopped at: {outputs.deepest_stage}")

st.subheader("Best parameters")
if outputs.best_params:
    st.code(outputs.best_params, language=None)
elif outputs.input_params:
    st.code(outputs.input_params, language=None)
    st.caption("From best trial in ho.report")
else:
    st.info("No parameters yet.")

st.subheader("Predicted properties (best trial)")
if outputs.properties:
    st.dataframe(
        pd.DataFrame([{"Stage": p.stage, "Detail": p.detail, "Status": p.status} for p in outputs.properties]),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No property data in ho.report yet.")

if outputs.failure_reason:
    st.caption(f"Outcome: {outputs.failure_reason}")

st.divider()
st.markdown("Next step: **Agent Strategy** — agent proposes reward changes based on this analysis.")
