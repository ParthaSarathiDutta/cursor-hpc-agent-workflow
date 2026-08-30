"""Agent Activity — current task, plan, and wait ETA."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import streamlit as st
from datetime import timedelta

from blast_lib.agent_status import load_agent_snapshot
from blast_lib.config import load_config

STATUS_ICON = {"active": "🟢", "complete": "✅", "idle": "⚪"}


def _format_elapsed(seconds: float) -> str:
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


@st.fragment(run_every=timedelta(seconds=10))
def activity_panel():
    config = load_config()
    snap = load_agent_snapshot(config)
    icon = STATUS_ICON.get(snap.status, "⚪")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Status", f"{icon} {snap.status.title()}")
    with c2:
        st.metric("Elapsed", _format_elapsed(snap.elapsed_seconds))
    with c3:
        st.metric("Estimated wait", snap.eta_label.split(" (")[0] if snap.eta_label else "—")

    st.subheader("Current task")
    st.write(snap.current_task)

    if snap.subagent:
        st.caption(f"Subagent: **{snap.subagent}**")

    st.subheader("Plan")
    if snap.plan_name:
        st.markdown(f"**{snap.plan_name}**")
    if snap.todos:
        for todo in snap.todos:
            badge = {"completed": "✅", "in_progress": "🔵", "pending": "⬜", "cancelled": "🚫"}.get(
                todo.status, "⬜"
            )
            st.markdown(f"{badge} {todo.content}")
        st.caption(snap.eta_label)
    else:
        st.info("No active plan file found. Plans are read from ~/.cursor/plans/.")

    st.subheader("Last action")
    st.code(snap.last_action)

    if snap.session_id:
        st.caption(f"Session: `{snap.session_id[:8]}…`")


st.title("Agent Activity")
st.caption("Auto-refreshes every 10 seconds")
activity_panel()
