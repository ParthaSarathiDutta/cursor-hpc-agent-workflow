"""Detailed view of one BLAST run."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from blast_lib.config import load_config, report_path
from blast_lib.metrics import best_so_far, stage_breakdown, summarize_run, top_k_trials
from blast_lib.parser import parse_ho_report

config = load_config()

st.title("Run Detail")
folder = st.selectbox("Run folder", config.run_folders)
rp = report_path(config, folder)

if not rp.is_file():
    st.warning(f"No report at {rp}. Use **Sync from Perlmutter** in the sidebar.")
    st.stop()

trials = parse_ho_report(rp)
summary = summarize_run(folder, trials)
curve = best_so_far(trials)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Best score", f"{summary.best_score:,.0f}" if summary.best_score else "—")
c2.metric("Trials", summary.trial_count)
c3.metric("Deepest stage", summary.deepest_stage)
c4.metric("Scored", summary.scored_count)

fig = go.Figure()
if curve:
    fig.add_trace(go.Scatter(x=[p["iteration"] for p in curve], y=[p["score"] for p in curve],
                             mode="lines", name="Score", line=dict(color="#64748b", width=1), opacity=0.5))
    fig.add_trace(go.Scatter(x=[p["iteration"] for p in curve], y=[p["best"] for p in curve],
                             mode="lines", name="Best so far", line=dict(color="#2563eb", width=2)))
fig.update_layout(template="plotly_dark", height=420,
                  title=f"Objective score — {folder}", xaxis_title="Iteration", yaxis_title="finalObj")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Top 5 trials")
top = top_k_trials(trials, k=5)
st.dataframe(pd.DataFrame(top)[["iteration", "score", "stage", "reason"]], use_container_width=True, hide_index=True)

st.subheader("Stage breakdown (all scored trials)")
st.bar_chart(stage_breakdown(trials))
