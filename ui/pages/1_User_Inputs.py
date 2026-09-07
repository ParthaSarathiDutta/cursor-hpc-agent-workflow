"""User Inputs — all paths provided by the user (nothing assumed)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import streamlit as st

from blast_lib.config import load_config
from blast_lib.remote import RemoteError, sbatch_dry_run_at_path, sbatch_submit_at_path, ssh_ping
from blast_lib.run_io import parse_model_json, read_remote_file
from blast_lib.user_session import UserRunSession, get_session, save_session

st.title("User Inputs")
st.caption("Provide every path yourself — the app does not assume run folders or data locations")

config = load_config()
ssh_ok, ssh_msg = ssh_ping(config)
session = get_session()

st.subheader("1. Training data")
session.training_data_path = st.text_input(
    "Training data path (Perlmutter)",
    value=session.training_data_path,
    placeholder="/global/cfs/cdirs/.../your_training_catalog",
    help="Full path to the DFT reference structure catalog",
)

st.divider()
st.subheader("2. Model (Tersoff)")
st.caption(f"Model type: **{session.model_type}**")
session.model_json_path = st.text_input(
    "model.json path",
    value=session.model_json_path,
    placeholder="/global/cfs/.../AgenticBLAST/your_run/model.json",
)

if st.button("Load model.json", disabled=not session.model_json_path.strip()):
    with st.spinner("Fetching model.json..."):
        text = None
        local = Path(session.model_json_path)
        if local.is_file():
            text = local.read_text()
        elif ssh_ok:
            text = read_remote_file(config, session.model_json_path.strip())
    if text:
        pair, n_params, preview = parse_model_json(text)
        session.model_loaded = True
        session.model_preview = preview
        session.element_pair = pair
        session.n_search_params = n_params
        save_session(session)
        st.success(f"Loaded — element pair: {pair or '?'}, searchable params: {n_params or '?'}")
    else:
        st.error("Could not read model.json at that path.")

if session.model_loaded and session.model_preview:
    with st.expander("model.json preview", expanded=False):
        st.code(session.model_preview, language="json")

st.divider()
st.subheader("3. Optimizer")
st.text_input(
    "Optimizer",
    value=session.optimizer,
    disabled=True,
    help="Monte Carlo Tree Search — runs until the Slurm job ends",
)

st.divider()
st.subheader("4. Run folder")
session.run_folder_path = st.text_input(
    "Run folder path (Perlmutter)",
    value=session.run_folder_path,
    placeholder="/global/cfs/cdirs/.../AgenticBLAST/your_run_folder",
    help="Full path to the BLAST run directory on Perlmutter",
)

st.divider()
if st.button("Connect", type="primary"):
    missing = []
    if not session.training_data_path.strip():
        missing.append("training data path")
    if not session.model_json_path.strip():
        missing.append("model.json path")
    if not session.run_folder_path.strip():
        missing.append("run folder path")
    if missing:
        st.error("Provide: " + ", ".join(missing))
    else:
        session.connected = True
        if session.run_folder_path not in session.saved_runs:
            session.saved_runs.append(session.run_folder_path)
        save_session(session)
        st.success("Connected. Go to **Analyze** to view status and parameters.")

if session.connected:
    st.info(
        f"Connected to run: `{session.run_folder_path}`\n\n"
        f"Training data: `{session.training_data_path}`\n\n"
        f"Model: `{session.model_json_path}`"
    )

st.divider()
st.subheader("Submit job (optional)")
if not ssh_ok:
    st.error(f"SSH unavailable: {ssh_msg}")
elif session.run_folder_path.strip():
    st.code(sbatch_dry_run_at_path(config, session.run_folder_path.strip()), language="bash")
    if st.checkbox("Confirm submit"):
        if st.button("sbatch"):
            try:
                st.success(sbatch_submit_at_path(config, session.run_folder_path.strip()))
            except RemoteError as exc:
                st.error(str(exc))
else:
    st.caption("Enter a run folder path above to enable submit.")

save_session(session)
