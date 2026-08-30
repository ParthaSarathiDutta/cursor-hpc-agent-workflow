"""Overview of all BLAST run folders."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import streamlit as st

from blast_lib.config import load_config, report_path
from blast_lib.metrics import summarize_run
from blast_lib.parser import parse_ho_report

config = load_config()

st.title("Run Overview")
st.caption(f"Data from {config.local_cache_path}")

cols = st.columns(len(config.run_folders))
for col, folder in zip(cols, config.run_folders):
    rp = report_path(config, folder)
    exists = rp.is_file()
    trials = parse_ho_report(rp) if exists else []
    summary = summarize_run(folder, trials, report_exists=exists)
    with col:
        st.subheader(folder)
        if not exists:
            st.warning("No ho.report — sync from Perlmutter")
        else:
            best = f"{summary.best_score:,.0f}" if summary.best_score else "—"
            st.metric("Best finalObj", best)
            st.metric("Trials", summary.trial_count)
            st.metric("Deepest stage", summary.deepest_stage)
            st.metric("Below 999k", summary.below_penalty_count)
