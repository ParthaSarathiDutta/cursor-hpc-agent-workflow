"""System checks — like NeuroTrack demo checklist, for local Streamlit hosting."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import streamlit as st

from blast_lib.config import load_config
from blast_lib.gemini_client import gemini_model, llm_available
from blast_lib.remote import ssh_ping
from blast_lib.run_catalog import load_catalog

st.title("System Checks")
st.caption("Verify local dashboard, API keys, cache, and Perlmutter SSH before using Agent Chat.")

config = load_config()
url = config.dashboard_url

st.markdown(
    f"""
    **Open in Safari or Chrome:** [{url}]({url})

    Streamlit needs a running Python server (unlike static GitHub Pages apps such as
    [NeuroTrack AI](https://parthasarathidutta.github.io/neurotrack-ai/)).
    Use the checks below to confirm everything is ready.
    """
)

checks: list[tuple[str, bool, str]] = []

# 1. Server (this page loading implies server is up)
checks.append(("Dashboard server", True, f"Responding — you are viewing {url}"))

# 2. Gemini
if llm_available(config):
    checks.append(("Gemini API key", True, f"Loaded — model `{gemini_model(config)}`"))
else:
    checks.append(
        (
            "Gemini API key",
            False,
            "Missing — add `GOOGLE_API_KEY` or `GEMINI_API_KEY` to repo-root `.env`",
        )
    )

# 3. Cached reports
entries = load_catalog(config, load_main1=False)
synced = [e for e in entries if e.report_exists]
if synced:
    checks.append(
        (
            "Cached ho.report",
            True,
            f"{len(synced)}/{len(entries)} folders synced at `{config.local_cache_path}`",
        )
    )
else:
    checks.append(
        (
            "Cached ho.report",
            False,
            "No synced reports — open **Run Dashboard** and Sync from Perlmutter",
        )
    )

# 4. SSH
ok_ssh, ssh_msg = ssh_ping(config, timeout=10)
checks.append(
    (
        "Perlmutter SSH",
        ok_ssh,
        f"Connected to `{config.ssh_host}`" if ok_ssh else f"Failed — {ssh_msg}",
    )
)

st.subheader("Status")
for name, ok, detail in checks:
    if ok:
        st.success(f"**{name}** — {detail}")
    else:
        st.error(f"**{name}** — {detail}")

st.subheader("Quick commands")
st.code(
    """# One-time: install persistent local hosting (macOS LaunchAgent)
./scripts/install-dashboard-agent.sh

# Verify + auto-start if down
./scripts/check-dashboard.sh

# Manual control (if LaunchAgent not installed)
./scripts/dashboard-dev.sh start
./scripts/dashboard-dev.sh status

# Refresh NERSC SSH (from project root)
./scripts/setup-sshproxy.sh""",
    language="bash",
)

col1, col2, col3 = st.columns(3)
with col1:
    if st.button("Recheck SSH", use_container_width=True):
        st.rerun()
with col2:
    if st.button("Open in Safari/Chrome", use_container_width=True):
        subprocess.Popen(["open", url])  # noqa: S603
        st.toast(f"Opened {url}")
with col3:
    if st.button("Run check-dashboard.sh", use_container_width=True):
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run(  # noqa: S603
            [str(root / "scripts" / "check-dashboard.sh")],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        st.code(result.stdout or result.stderr or "(no output)")
