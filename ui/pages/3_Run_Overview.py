"""Overview of user-connected BLAST runs."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import streamlit as st

from blast_lib.config import load_config
from blast_lib.metrics import summarize_run
from blast_lib.parser import parse_ho_report
from blast_lib.user_session import cached_report_path, connected_run_paths, get_session, run_folder_name

config = load_config()
session = get_session()
run_paths = connected_run_paths(session)

st.title("Run Overview")
st.caption(f"Cached data under {config.local_cache_path}")

if not run_paths:
    st.warning("No runs connected. Go to **User Inputs**, enter paths, and click **Connect**.")
    st.stop()

cols = st.columns(min(len(run_paths), 4))
for col, run_path in zip(cols, run_paths):
    name = run_folder_name(run_path)
    rp = cached_report_path(config, run_path)
    exists = rp.is_file()
    trials = parse_ho_report(rp) if exists else []
    summary = summarize_run(name, trials, report_exists=exists)
    with col:
        st.subheader(name)
        st.caption(run_path)
        if not exists:
            st.warning("No ho.report — sync from **Analyze** or sidebar")
        else:
            best = f"{summary.best_score:,.0f}" if summary.best_score else "—"
            st.metric("Best finalObj", best)
            st.metric("Trials", summary.trial_count)
            st.metric("Deepest stage", summary.deepest_stage)
            st.metric("Below 999k", summary.below_penalty_count)
