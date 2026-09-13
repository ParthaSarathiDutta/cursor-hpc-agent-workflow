"""Detailed view of one BLAST run."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from blast_lib.config import load_config
from blast_lib.metrics import best_so_far, stage_breakdown, top_k_trials
from blast_lib.parser import parse_ho_report
from blast_lib.run_catalog import find_report_path, list_catalog_paths, load_catalog_entry
from blast_lib.user_session import get_session

config = load_config()
session = get_session()
paths = list_catalog_paths(config, session)

st.title("Run Detail")

if not paths:
    st.warning("No folders on **Run Dashboard**.")
    st.stop()

labels = {p.split("/")[-1]: p for p in paths}
pick = st.selectbox("Folder", list(labels.keys()))
run_path = labels[pick]
entry = load_catalog_entry(config, run_path)
rp = find_report_path(config, run_path)

st.caption(entry.strategy)

if not rp.is_file():
    st.warning("No report — sync from **Run Dashboard**.")
    st.stop()

trials = parse_ho_report(rp)
curve = best_so_far(trials)

c1, c2, c3 = st.columns(3)
c1.metric("Best stage (best set)", entry.best_stage)
c2.metric("Trials", entry.trial_count)
c3.metric("Completed all", "yes" if entry.completed_all else "no")

fig = go.Figure()
if curve:
    fig.add_trace(
        go.Scatter(
            x=[p["iteration"] for p in curve],
            y=[p["score"] for p in curve],
            mode="lines",
            name="Score",
            line=dict(color="#64748b", width=1),
            opacity=0.5,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[p["iteration"] for p in curve],
            y=[p["best"] for p in curve],
            mode="lines",
            name="Best so far",
            line=dict(color="#2563eb", width=2),
        )
    )
fig.update_layout(template="plotly_dark", height=420, title=f"Best-so-far — {pick}")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Top 5 trials (best sets)")
top = top_k_trials(trials, k=5)
st.dataframe(pd.DataFrame(top)[["iteration", "score", "stage", "reason"]], use_container_width=True, hide_index=True)

st.subheader("Stage breakdown (all trials — informational only)")
st.caption("Strategy decisions use the best set only, not this chart.")
st.bar_chart(stage_breakdown(trials))
