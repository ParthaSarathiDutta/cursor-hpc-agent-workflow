"""BLAST Run Dashboard — human-in-the-loop."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blast_lib.env import load_repo_dotenv  # noqa: E402

load_repo_dotenv()

import streamlit as st

from blast_lib.config import load_config
from blast_lib.gemini_client import llm_available
from blast_lib.remote import ssh_ping, sync_all_runs
from blast_lib.run_catalog import list_catalog_paths
from blast_lib.user_session import get_session

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
    st.caption("Human-in-the-loop · Perlmutter via SSH")

    ok, msg = _ssh_status(config.ssh_host)
    if st.button("Recheck SSH", use_container_width=True):
        _ssh_status.clear()
        st.rerun()

    if ok:
        st.success(f"SSH: {config.ssh_host}")
    else:
        st.error(f"SSH failed — {msg}")

    if llm_available(config):
        st.success("Gemini: ready")
    else:
        st.warning("Gemini: add key to .env")

    st.page_link("pages/0_System_Checks.py", label="System Checks", icon="✅")

    session = get_session()
    paths = list_catalog_paths(config, session)

    st.divider()
    if paths and st.button("Sync all folders", use_container_width=True, disabled=not ok):
        with st.spinner("Syncing..."):
            results = sync_all_runs(config, paths)
        for label, status in results.items():
            st.write(f"**{label}:** {status}")
    elif not paths:
        st.caption("Set `run_folders` in config/ui.yaml")

    st.divider()
    st.code(f"Cache: {config.local_cache_path}\nRoot: {config.blast_root}", language=None)

st.title("Welcome")
st.markdown(
    """
    | Step | Page |
    |------|------|
    | **1. View runs** | **Run Dashboard** — each folder, strategy, best set, performance |
    | **2. Discuss** | **Agent Chat** — ask questions; agent uses synced run context |
    | **3. Act** | **Submit Next Job** — you instruct changes; confirm sbatch |
    | **Deep dive** | Run Detail, Compare, Jobs, Agent Activity |
    """
)
st.info("Open **Run Dashboard** first. Sync folders from Perlmutter, then chat or submit the next job.")
st.warning("Use **Safari or Chrome** at http://127.0.0.1:8501 — not Cursor's built-in browser.")

with st.expander("Quick start"):
    st.code(
        "./scripts/install-dashboard-agent.sh   # one-time persistent hosting\n"
        "./scripts/check-dashboard.sh           # verify",
        language="bash",
    )
