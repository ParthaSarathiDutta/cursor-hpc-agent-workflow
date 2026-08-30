"""Side-by-side comparison of run folders."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import pandas as pd
import streamlit as st

from blast_lib.config import load_config, report_path
from blast_lib.metrics import summarize_run, top_k_trials
from blast_lib.parser import parse_ho_report

config = load_config()

st.title("Compare Runs")

rows = []
for folder in config.run_folders:
    rp = report_path(config, folder)
    exists = rp.is_file()
    trials = parse_ho_report(rp) if exists else []
    s = summarize_run(folder, trials, report_exists=exists)
    rows.append({
        "Folder": folder,
        "Report": "yes" if exists else "no",
        "Trials": s.trial_count,
        "Best finalObj": s.best_score,
        "Deepest stage": s.deepest_stage,
        "Below 999k": s.below_penalty_count,
    })

df = pd.DataFrame(rows)
st.dataframe(df, use_container_width=True, hide_index=True)

st.subheader("Best trial per folder")
best_rows = []
for folder in config.run_folders:
    rp = report_path(config, folder)
    if not rp.is_file():
        continue
    trials = parse_ho_report(rp)
    top = top_k_trials(trials, k=1)
    if top:
        best_rows.append({"Folder": folder, "Score": top[0]["score"], "Stage": top[0]["stage"],
                          "Reason": top[0]["reason"][:120]})
if best_rows:
    st.dataframe(pd.DataFrame(best_rows), use_container_width=True, hide_index=True)
else:
    st.info("Sync run data to compare best trials.")
