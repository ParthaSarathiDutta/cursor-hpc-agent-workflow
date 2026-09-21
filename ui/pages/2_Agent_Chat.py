"""Agent Chat — agentic assistant with tool calling."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import streamlit as st

from blast_lib.agent_chat import ChatMessage, build_context_summary, chat_reply, llm_available
from blast_lib.config import load_config
from blast_lib.gemini_client import gemini_model
from blast_lib.user_session import get_session

st.title("Agent Chat")

config = load_config()
session = get_session()

st.caption(
    f"**Agentic** — model `{gemini_model(config)}` calls tools to read ho.report / main1.py on demand."
)

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

if not llm_available(config):
    st.warning(
        "Agent Chat uses **Google Gemini**. Set GOOGLE_API_KEY or GEMINI_API_KEY in `.env`."
    )

with st.expander("Available tools", expanded=False):
    st.markdown(
        """
| Tool | What it does |
|------|----------------|
| `list_run_folders` | All folders + best stage |
| `get_folder_overview` | Summary + main1 checkpoints |
| `get_trial_parameters` | Tersoff params for rank N |
| `get_trial_details` | Full trial metrics |
| `get_property_metrics` | One property (phonon, elastic, …) |
| `get_checkpoint_thresholds` | main1.py rules |
| `compare_top_trials` | Top K in one folder |
| `find_best_across_folders` | Best property metric across folders |
| `list_blast_run_dirs` | Run dirs on Perlmutter (SSH) |
| `read_input_txt` / `write_input_txt` | AgenticBLAST `input.txt` on Perlmutter |
| `get_launch_commands` | Preview salloc + parallel (you run on PM) |
| `preview_interactive_launch` | Preview one-shot dashboard SSH launch (no execute) |
"""
    )

with st.expander("Run folders (index only — details via tools)", expanded=False):
    st.text(build_context_summary(config, session))

for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Ask anything — the agent will fetch data with tools...")
if prompt:
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    history = [ChatMessage(role=m["role"], content=m["content"]) for m in st.session_state.chat_messages[:-1]]
    with st.spinner("Thinking (may call tools)..."):
        result = chat_reply(config, session, history, prompt)
    st.session_state.chat_messages.append({"role": "assistant", "content": result.text})
    st.rerun()

if st.button("Clear chat"):
    st.session_state.chat_messages = []
    st.rerun()

st.caption("After discussing here, use **Submit Next Job** to queue what should run on Perlmutter.")
