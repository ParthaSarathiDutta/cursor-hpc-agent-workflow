"""Agent Strategy — agent proposes reward/objective design (not a user input)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import streamlit as st

from blast_lib.config import load_config
from blast_lib.metrics import summarize_run
from blast_lib.parser import parse_ho_report
from blast_lib.strategy_llm import generate_llm_strategy, llm_available
from blast_lib.strategy_rules import suggest_for_run
from blast_lib.user_session import cached_report_path, connected_run_paths, get_session, run_folder_name

config = load_config()
session = get_session()
run_paths = connected_run_paths(session)

st.title("Agent Strategy")
st.caption("Agent designs reward structures — polymorph scoring, objective changes in main1.py")

st.markdown(
    """
    **Not a user input.** After you **Analyze** a connected run, the agent proposes how to change the
    **reward / objective** (e.g. hybrid CE-only dual polymorph, tighter bounds, new run folder).
    User paths live on **User Inputs**; status and parameters on **Analyze**.
    """
)

if not run_paths:
    st.warning("Connect a run on **User Inputs** and analyze it before requesting strategy.")
    st.stop()

run_path = st.selectbox("Run to strategize", run_paths, format_func=run_folder_name)
name = run_folder_name(run_path)
rp = cached_report_path(config, run_path)

st.caption(run_path)

if not rp.is_file():
    st.warning("No ho.report cached — sync on **Analyze** first.")
    st.stop()

trials = parse_ho_report(rp)
summary = summarize_run(name, trials)
suggestions = suggest_for_run(name, trials, summary)

st.subheader("Agent suggestions (reward / next run)")
for s in suggestions:
    with st.expander(f"[{s.priority.upper()}] {s.title}", expanded=s.priority == "high"):
        st.write(s.detail)

st.divider()
st.subheader("LLM suggestions (optional)")
if llm_available():
    if st.button("Generate LLM strategy"):
        prompt = (
            f"BLAST Tersoff fitting for {name} at {run_path}. "
            f"Best score: {summary.best_score}. Deepest stage: {summary.deepest_stage}. "
            "Suggest how the agent should change the reward/objective (main1.py polymorph strategy) "
            "in 3 bullets. Do not ask the user to pick a preset — propose an agent action."
        )
        st.write(generate_llm_strategy(prompt))
else:
    st.info("Set GOOGLE_API_KEY to enable LLM strategy suggestions.")
