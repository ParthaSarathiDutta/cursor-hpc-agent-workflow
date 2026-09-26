"""Autonomous iterative fitting — single folder, interactive salloc cycles."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import streamlit as st

from blast_lib.agenticblast_submit import SubmitPathError, list_blast_run_dirs, normalize_run_path
from blast_lib.config import load_config
from blast_lib.iterative_loop.controller import IterativeRunController, is_workflow_active
from blast_lib.iterative_loop.state import begin_workflow, load_state, request_stop
from blast_lib.remote import ssh_ping

ROOT = Path(__file__).resolve().parents[2]
RUNNER_SCRIPT = ROOT / "scripts" / "iterative-loop-dev.sh"

config = load_config()
st.title("Autonomous Iterative Fitting")
st.caption("Single run folder · interactive salloc + RunBOP · changemodel.json.py between cycles")

ssh_ok, ssh_msg = ssh_ping(config, timeout=15)
if not ssh_ok:
    st.error(f"SSH unavailable: {ssh_msg}")

state = load_state(config)
active = is_workflow_active(state)

# String keys — safe when Streamlit still has a pre-RUNNING_INTERACTIVE Phase enum cached.
PHASE_LABELS: dict[str, str] = {
    "IDLE": "Idle.",
    "SUBMITTING": "Preparing input.txt…",
    "RUNNING_INTERACTIVE": "Interactive salloc + RunBOP running…",
    "WAITING_FOR_JOB": "Waiting for Slurm job…",
    "ANALYZING_BEST_SET": "Finding best set…",
    "UPDATING_RANGES": "Updating parameter ranges…",
    "STARTING_NEXT_CYCLE": "Starting next cycle…",
    "COMPLETED": "Workflow complete.",
    "FAILED": "Failed.",
    "STOPPED": "Stopped.",
}
TERMINAL_PHASE_VALUES = frozenset({"IDLE", "COMPLETED", "FAILED", "STOPPED"})

def _ensure_runner_started() -> None:
    if not RUNNER_SCRIPT.is_file():
        st.warning("Missing scripts/iterative-loop-dev.sh")
        return
    subprocess.run(["bash", str(RUNNER_SCRIPT), "start"], cwd=ROOT, check=False)


col_a, col_b = st.columns(2)
with col_a:
    if st.button("Refresh status"):
        IterativeRunController(config).tick()
        st.rerun()
with col_b:
    st.caption(f"Runner `{RUNNER_SCRIPT.name} start` keeps the loop alive when this tab is closed.")

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

st.write("**Current phase:**", PHASE_LABELS.get(state.phase, state.phase))
if state.status_message:
    st.info(state.status_message)
if state.stop_requested:
    st.warning(
        "Stop requested — no further cycles will start. "
        "If an interactive allocation is still running, it finishes unless scancel succeeded."
    )
if state.active_job_id:
    st.write(f"**Allocation / job ID:** `{state.active_job_id}`")
if state.slurm_state:
    st.write(f"**Slurm state:** {state.slurm_state}")
if state.last_launch_returncode is not None:
    st.write(f"**Last interactive SSH exit code:** {state.last_launch_returncode}")
if state.last_completed_cycle:
    st.write(f"**Last completed cycle:** {state.last_completed_cycle}")
if state.last_best_score is not None:
    st.write(f"**Last best score:** {state.last_best_score}")
if state.last_best_iteration is not None:
    st.write(f"**Last best iteration:** {state.last_best_iteration}")
if state.last_range_update:
    st.write(f"**Last range update:** {state.last_range_update}")
if state.scored_trial_count_before is not None:
    st.caption(
        f"Scored trials this cycle: before={state.scored_trial_count_before}, "
        f"after={state.scored_trial_count_after}"
    )
if state.error:
    st.error(state.error)

if state.phase == "RUNNING_INTERACTIVE":
    st.caption(
        "Runner holds SSH for this allocation. When it ends and ho.report gains new trials, "
        "RangeAgent updates ranges."
    )

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
    walltime = st.text_input("Time per run (HH:MM:SS)", value=state.walltime or "00:10:00")
    total_cycles = st.number_input("Number of runs", min_value=1, max_value=50, value=3)

    if st.button("Start", type="primary", disabled=not ssh_ok):
        try:
            path = normalize_run_path(config, run_folder)
        except SubmitPathError as exc:
            st.error(str(exc))
        else:
            begin_workflow(
                config,
                run_folder=path,
                walltime=walltime.strip(),
                total_cycles=int(total_cycles),
            )
            _ensure_runner_started()
            IterativeRunController(config).tick()
            st.success("Workflow started. Runner will continue in the background.")
            st.rerun()

if active or state.phase not in ("IDLE", "COMPLETED"):
    if st.button("Stop workflow"):
        request_stop(config)
        st.rerun()

st.divider()
st.caption("See docs/autonomous-iterative-loop.md. Uses changemodel.json.py (not startmodel.py).")
