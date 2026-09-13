"""Slurm job monitor."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import streamlit as st

from blast_lib.config import load_config
from blast_lib.remote import squeue_me, tail_log

config = load_config()

st.title("Slurm Jobs")
st.caption(f"Monitor queue — submit from **Submit Next Job**")

st.subheader("Your queue")
st.code(squeue_me(config), language="bash")

st.subheader("Tail job log")
job_id = st.text_input("Job ID")
if job_id:
    st.code(tail_log(config, job_id), language="bash")

st.divider()
st.caption("To submit a new BLAST search, use the **User Inputs** page.")
