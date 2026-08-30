"""Rule-based and optional LLM strategy suggestions."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import streamlit as st

from blast_lib.config import load_config, report_path
from blast_lib.metrics import summarize_run
from blast_lib.parser import parse_ho_report
from blast_lib.strategy_llm import generate_llm_strategy, llm_available
from blast_lib.strategy_rules import suggest_for_run

config = load_config()

st.title("Strategy Advisor")
st.caption("Top-k focused suggestions per strategy.md")

folder = st.selectbox("Run folder", config.run_folders)
rp = report_path(config, folder)

if not rp.is_file():
    st.warning("Sync run data first.")
    st.stop()

trials = parse_ho_report(rp)
summary = summarize_run(folder, trials)
suggestions = suggest_for_run(folder, trials, summary)

st.subheader("Rule-based suggestions")
for s in suggestions:
    with st.expander(f"[{s.priority.upper()}] {s.title}", expanded=s.priority == "high"):
        st.write(s.detail)

st.divider()
st.subheader("LLM suggestions (optional)")
if llm_available():
    if st.button("Generate LLM strategy"):
        prompt = f"BLAST Tersoff fitting for {folder}. Best score: {summary.best_score}. Deepest: {summary.deepest_stage}. Suggest next run strategy in 3 bullets."
        st.write(generate_llm_strategy(prompt))
else:
    st.info("Set GOOGLE_API_KEY environment variable to enable LLM suggestions.")
