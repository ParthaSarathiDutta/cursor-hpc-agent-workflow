"""Side-by-side comparison of user-connected runs."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import pandas as pd
import streamlit as st

from blast_lib.config import load_config
from blast_lib.metrics import summarize_run, top_k_trials
from blast_lib.parser import parse_ho_report
from blast_lib.user_session import cached_report_path, connected_run_paths, get_session, run_folder_name

config = load_config()
session = get_session()
run_paths = connected_run_paths(session)

st.title("Compare Runs")

if not run_paths:
    st.warning("No runs connected. Go to **User Inputs** first.")
    st.stop()

rows = []
for run_path in run_paths:
    name = run_folder_name(run_path)
    rp = cached_report_path(config, run_path)
    exists = rp.is_file()
    trials = parse_ho_report(rp) if exists else []
    s = summarize_run(name, trials, report_exists=exists)
    rows.append(
        {
            "Run": name,
            "Path": run_path,
            "Report": "yes" if exists else "no",
            "Trials": s.trial_count,
            "Best finalObj": s.best_score,
            "Deepest stage": s.deepest_stage,
            "Below 999k": s.below_penalty_count,
        }
    )

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.subheader("Best trial per run")
best_rows = []
for run_path in run_paths:
    name = run_folder_name(run_path)
    rp = cached_report_path(config, run_path)
    if not rp.is_file():
        continue
    trials = parse_ho_report(rp)
    top = top_k_trials(trials, k=1)
    if top:
        best_rows.append(
            {
                "Run": name,
                "Score": top[0]["score"],
                "Stage": top[0]["stage"],
                "Reason": top[0]["reason"][:120],
            }
        )

if best_rows:
    st.dataframe(pd.DataFrame(best_rows), use_container_width=True, hide_index=True)
else:
    st.info("Sync run data on **Analyze** to compare best trials.")
