"""BLAST Run Dashboard — local Streamlit app."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from blast_lib.config import load_config
from blast_lib.remote import ssh_ping, sync_all_runs
from blast_lib.user_session import connected_run_paths, get_session

st.set_page_config(
    page_title="BLAST Dashboard",
    page_icon="⚛",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; }
    div[data-testid="stMetricValue"] { font-size: 1.4rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

config = load_config()


@st.cache_data(ttl=60)
def _ssh_status(host: str) -> tuple[bool, str]:
    from blast_lib.config import UIConfig

    return ssh_ping(UIConfig(ssh_host=host), timeout=15)


with st.sidebar:
    st.title("BLAST Dashboard")
    st.caption("Local UI · Perlmutter via SSH")

    ok, msg = _ssh_status(config.ssh_host)
    if st.button("Recheck SSH", use_container_width=True):
        _ssh_status.clear()
        st.rerun()

    if ok:
        st.success(f"Perlmutter SSH: connected ({config.ssh_host})")
    else:
        st.error(f"Perlmutter SSH: failed — {msg}")
        st.markdown("Run `./scripts/setup-sshproxy.sh` then test: `ssh perlmutter echo ok`")

    session = get_session()
    run_paths = connected_run_paths(session)

    st.divider()
    if not run_paths:
        st.caption("Connect runs on **User Inputs** to enable sync.")
    elif st.button("Sync connected runs", use_container_width=True, disabled=not ok):
        with st.spinner("Rsync run reports (may take ~30s)..."):
            results = sync_all_runs(config, run_paths)
        for label, status in results.items():
            if status == "ok":
                st.success(f"{label}: synced")
            else:
                st.warning(f"{label}: {status}")
    elif not ok:
        st.caption("Sync disabled until SSH works.")

    st.divider()
    st.markdown("**Paths**")
    st.code(
        f"SSH:  {config.ssh_host}\n"
        f"Cache: {config.local_cache_path}\n"
        f"Remote default: {config.blast_root}",
        language=None,
    )

st.title("Welcome")
st.markdown(
    """
    | Step | Page |
    |------|------|
    | **1. User inputs** | **User Inputs** — training data path, Tersoff model (`model.json`), MCTS, run folder path |
    | **2. Analyze** | **Analyze** — sync and view status, best parameters, predicted properties |
    | **3. Agent** | **Agent Strategy** — reward / objective design (not a user input) |
    | **Monitor** | Overview, Run Detail, Compare, Jobs, Agent Activity |
    """
)
st.info(
    "You provide every path — the app does not assume run folders. "
    "Start on **User Inputs**, click **Connect**, then go to **Analyze**."
)
st.warning(
    "Use **Safari or Chrome** at http://127.0.0.1:8501 — Cursor's built-in browser "
    "often shows *Connection error* with Streamlit."
)

with st.expander("Quick start"):
    st.code("./scripts/run-dashboard.sh", language="bash")
    st.markdown(
        "If the browser shows *Connection refused*, the dashboard is not running — "
        "start it with the command above, then open **http://localhost:8501**."
    )
