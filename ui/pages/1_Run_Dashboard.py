"""Run Dashboard — all folders, best set, and performance."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import pandas as pd
import streamlit as st

from blast_lib.config import load_config
from blast_lib.remote import RemoteError, ssh_ping, sync_run_at_path
from blast_lib.parser import parse_ho_report
from blast_lib.metrics import top_k_trials
from blast_lib.trial_details import analyze_best_trial, format_analysis_text
from blast_lib.run_catalog import find_report_path, load_catalog, load_catalog_entry, resolve_run_path
from blast_lib.notifications import findings_summary, mailto_link
from blast_lib.user_session import get_session

st.title("Run Dashboard")
st.caption("Best set per folder — human-in-the-loop starting point")

config = load_config()
session = get_session()
ssh_ok, _ = ssh_ping(config)

col_a, col_b = st.columns([1, 1])
with col_a:
    if st.button("Sync all folders", disabled=not ssh_ok):
        from blast_lib.run_catalog import list_catalog_paths

        for path in list_catalog_paths(config, session):
            with st.spinner(f"Syncing {path.split('/')[-1]}..."):
                try:
                    sync_run_at_path(config, path)
                except RemoteError as exc:
                    st.warning(f"{path}: {exc}")
        st.success("Sync complete")
        st.rerun()

with col_b:
    extra = st.text_input("Add folder path or name", placeholder="ML-Tersoff-1_PE_hybrid or full path")
    if st.button("Add to list") and extra.strip():
        path = resolve_run_path(config, extra.strip())
        if path not in session.saved_runs:
            session.saved_runs.append(path)
        from blast_lib.user_session import save_session

        save_session(session)
        st.rerun()

entries = load_catalog(config, session)

if not entries:
    st.warning("No folders configured. Add `run_folders` in config/ui.yaml or use **Add folder** above.")
    st.stop()

rows = []
for e in entries:
    perf = "Completed all stages" if e.completed_all else (e.best.failure_reason or "—")
    if len(perf) > 80:
        perf = perf[:80] + "..."
    rows.append(
        {
            "Folder": e.name,
            "Strategy": e.strategy,
            "Best stage": e.best_stage,
            "Best set outcome": perf,
            "Trials": e.trial_count if e.report_exists else "—",
            "Report": "yes" if e.report_exists else "no",
        }
    )

st.subheader("Folders at a glance")
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.divider()
st.subheader("Best set detail (per folder)")

for entry in entries:
    with st.expander(f"{entry.name} — best stage: {entry.best_stage}", expanded=(entry.name == entries[0].name)):
        if not entry.report_exists:
            st.warning("Sync ho.report first.")
            continue
        rp = find_report_path(config, entry.path)
        top = top_k_trials(parse_ho_report(rp), k=1)
        if not top:
            st.info("No scored trials.")
            continue
        analysis = analyze_best_trial(top[0], entry.name)
        st.markdown(format_analysis_text(entry.name, top[0], analysis, entry.checkpoint_config or {}))
        with st.expander("Raw best-set parameters"):
            st.code(top[0].get("input_params") or "—", language=None)

st.info("Ask questions in **Agent Chat** or instruct the next run in **Submit Next Job**.")

st.divider()
st.subheader("Share findings")
st.caption(f"Dashboard link: {config.dashboard_url}")
summary = findings_summary(config, session)
st.download_button("Download findings (.txt)", summary, file_name="blast_findings.txt")
mailto = mailto_link(config, session)
if mailto:
    st.markdown(f"[Email findings to {config.notify_email}]({mailto})")
else:
    st.caption("Set `notify_email` in config/ui.yaml to enable email link.")
