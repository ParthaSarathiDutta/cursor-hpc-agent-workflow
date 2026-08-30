"""BLAST Run Dashboard — local Streamlit app."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is on path regardless of how Streamlit is launched.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from blast_lib.config import load_config
from blast_lib.remote import ssh_ping, sync_all_runs

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


@st.cache_data(ttl=30)
def _ssh_status(host: str) -> tuple[bool, str]:
    from blast_lib.config import UIConfig

    return ssh_ping(UIConfig(ssh_host=host), timeout=5)


with st.sidebar:
    st.title("BLAST Dashboard")
    st.caption("Local UI · Perlmutter via SSH")

    ok, msg = _ssh_status(config.ssh_host)
    if ok:
        st.success(f"Perlmutter SSH: connected ({config.ssh_host})")
    else:
        st.error(f"Perlmutter SSH: failed")
        st.caption(msg)
        st.markdown(
            "Run `./scripts/setup-sshproxy.sh` then test: `ssh perlmutter echo ok`"
        )

    st.divider()
    if st.button("Sync from Perlmutter", use_container_width=True, disabled=not ok):
        with st.spinner("Rsync run reports (may take ~30s)..."):
            results = sync_all_runs(config)
        for folder, status in results.items():
            if status == "ok":
                st.success(f"{folder}: synced")
            else:
                st.warning(f"{folder}: {status}")
    elif not ok:
        st.caption("Sync disabled until SSH works.")

    st.divider()
    st.markdown("**Paths**")
    st.code(
        f"SSH:  {config.ssh_host}\n"
        f"Cache: {config.local_cache_path}\n"
        f"Remote: {config.blast_root}",
        language=None,
    )

st.title("Welcome")
st.markdown(
    "Use the sidebar pages to monitor **agent activity**, **BLAST runs**, "
    "**Slurm jobs**, and **strategy** suggestions."
)
st.info("Open **Agent Activity** for live status while the Cursor agent is working.")
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
