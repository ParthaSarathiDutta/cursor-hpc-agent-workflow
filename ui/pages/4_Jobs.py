"""Slurm job monitor and submit."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import streamlit as st

from blast_lib.config import load_config
from blast_lib.remote import RemoteError, sbatch_dry_run, sbatch_submit, squeue_me, tail_log

config = load_config()

st.title("Slurm Jobs")
st.caption(f"Remote host: {config.ssh_host}")

st.subheader("Your queue")
st.code(squeue_me(config), language="bash")

st.subheader("Tail job log")
job_id = st.text_input("Job ID")
if job_id:
    st.code(tail_log(config, job_id), language="bash")

st.divider()
st.subheader("Submit job")
run_folder = st.selectbox("Run folder on Perlmutter", config.run_folders)
st.text(f"Account (edit in slurm script): {config.gpu_account}")
st.code(sbatch_dry_run(config, run_folder), language="bash")

confirm = st.checkbox("I confirm I want to submit this job")
if st.button("Submit via sbatch", type="primary", disabled=not confirm):
    try:
        out = sbatch_submit(config, run_folder)
        st.success(out)
    except RemoteError as exc:
        st.error(str(exc))
