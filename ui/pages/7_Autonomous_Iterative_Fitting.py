"""Autonomous iterative fitting — NERSC batch Slurm dependency chain."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import streamlit as st

from blast_lib.agenticblast_submit import SubmitPathError, list_blast_run_dirs, normalize_run_path
from blast_lib.config import load_config
from blast_lib.iterative_loop.controller import IterativeRunController, is_workflow_active
from blast_lib.iterative_loop.state import load_state, request_stop
from blast_lib.remote import ssh_ping

config = load_config()
st.title("Autonomous Iterative Fitting")
st.caption(
    "Single run folder · Slurm batch GPU + Range jobs on NERSC · "
    "changemodel.json.py between cycles · Mac not required after Start"
)

ssh_ok, ssh_msg = ssh_ping(config, timeout=15)
if not ssh_ok:
    st.error(f"SSH unavailable: {ssh_msg}")

state = load_state(config)
active = is_workflow_active(state)

PHASE_LABELS: dict[str, str] = {
    "IDLE": "Idle.",
    "SUBMITTING": "Preparing…",
    "QUEUED_ON_NERSC": "Queued on NERSC (Slurm chain submitted).",
    "RUNNING_ON_NERSC": "Running on NERSC (GPU / Range jobs).",
    "RUNNING_INTERACTIVE": "Interactive salloc + RunBOP (legacy).",
    "WAITING_FOR_JOB": "Waiting for Slurm job…",
    "ANALYZING_BEST_SET": "Finding best set…",
    "UPDATING_RANGES": "Updating parameter ranges…",
    "STARTING_NEXT_CYCLE": "Starting next cycle…",
    "COMPLETED": "Workflow complete.",
    "FAILED": "Failed.",
    "STOPPED": "Stopped.",
}
TERMINAL_PHASE_VALUES = frozenset({"IDLE", "COMPLETED", "FAILED", "STOPPED"})

col_a, col_b = st.columns(2)
with col_a:
    if st.button("Refresh status"):
        folder = state.run_folder
        if folder:
            IterativeRunController(config).sync_from_remote(folder)
        else:
            IterativeRunController(config).tick()
        st.rerun()
with col_b:
    st.caption("Refresh pulls `<run_folder>/.agentic_loop/workflow.json` from Perlmutter.")

st.divider()
st.subheader("Status")

if state.phase in TERMINAL_PHASE_VALUES:
    status_label = "IDLE" if state.phase == "IDLE" else state.phase
else:
    status_label = "RUNNING"

st.metric("Overall", status_label)
c1, c2, c3 = st.columns(3)
with c1:
    cycle_show = state.current_cycle if state.current_cycle else "—"
    st.metric("Cycle", f"{cycle_show} / {state.total_cycles or '—'}")
with c2:
    remaining = state.remaining_cycles() if state.total_cycles else "—"
    st.metric("Remaining cycles", remaining)
with c3:
    st.metric("Phase", state.phase)

if state.execution_mode:
    st.caption(f"Execution mode: **{state.execution_mode}**")
if state.nersc_workflow_status:
    st.caption(f"NERSC workflow status: **{state.nersc_workflow_status}**")

st.write("**Current phase:**", PHASE_LABELS.get(state.phase, state.phase))
if state.status_message:
    st.info(state.status_message)
if state.stop_requested:
    st.warning("Stop requested — pending Slurm jobs were cancelled where possible.")
if state.active_job_id:
    st.write(f"**Active Slurm job ID (last seen):** `{state.active_job_id}`")
if state.run_folder:
    st.caption(f"Authoritative state: `{state.run_folder.rstrip('/')}/.agentic_loop/workflow.json`")
if state.last_completed_cycle:
    st.write(f"**Last completed cycle:** {state.last_completed_cycle}")
if state.last_best_score is not None:
    st.write(f"**Last best score:** {state.last_best_score}")
if state.last_best_iteration is not None:
    st.write(f"**Last best iteration:** {state.last_best_iteration}")
if state.last_range_update:
    st.write(f"**Last range update:** {state.last_range_update}")
if state.error:
    st.error(state.error)

st.divider()
st.subheader("Start workflow")

if active:
    st.warning("A workflow is in progress. Stop it before starting a new one.")
else:
    try:
        remote_dirs = list_blast_run_dirs(config) if ssh_ok else []
    except Exception:
        remote_dirs = []

    folder_default = state.run_folder or (remote_dirs[0] if remote_dirs else "ML-Tersoff-1_PE")
    run_folder = st.text_input("Run folder (name or absolute path)", value=folder_default)
    walltime = st.text_input("GPU time per cycle (HH:MM:SS)", value=state.walltime or "04:00:00")
    total_cycles = st.number_input("Number of cycles", min_value=1, max_value=50, value=3)

    if st.button("Start", type="primary", disabled=not ssh_ok):
        try:
            path = normalize_run_path(config, run_folder)
        except SubmitPathError as exc:
            st.error(str(exc))
        else:
            ctrl = IterativeRunController(config)
            result = ctrl.submit_batch_workflow(path, walltime.strip(), int(total_cycles))
            if result.phase == "FAILED":
                st.error(result.error or "Submit failed.")
            else:
                st.success(
                    "Slurm dependency chain submitted on NERSC. "
                    "You can close this Mac; use Refresh to reconnect."
                )
            st.rerun()

if active or state.phase not in ("IDLE", "COMPLETED"):
    if st.button("Stop workflow"):
        request_stop(config)
        st.rerun()

st.divider()
st.caption("See docs/autonomous-iterative-loop.md. GPU→Range: afterany; Range→next GPU: afterok.")
