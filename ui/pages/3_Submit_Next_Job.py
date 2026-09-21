"""Submit Next Job — input.txt on Perlmutter + manual salloc / parallel launch."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import streamlit as st

from blast_lib.agenticblast_submit import (
    SubmitPathError,
    format_input_txt_lines,
    format_parallel_command,
    format_salloc_command,
    list_blast_run_dirs,
    normalize_run_path,
    preview_interactive_launch_command,
    read_input_txt,
    run_batch_submit,
    run_interactive_launch_stream,
    write_input_txt_content,
)
from blast_lib.config import load_config
from blast_lib.job_instructions import JobInstruction, load_instruction, plan_summary, save_instruction
from blast_lib.remote import RemoteError, ssh_ping
from blast_lib.run_catalog import list_catalog_paths
from blast_lib.user_session import get_session

st.title("Submit Next Job")
st.caption(
    "Edit input.txt and launch commands, write input.txt on Perlmutter, then run Step A/B on a GPU node"
)

config = load_config()
session = get_session()
ssh_ok, ssh_msg = ssh_ping(config)

catalog_paths = list_catalog_paths(config, session)
if not catalog_paths:
    st.warning("No run folders. Configure `run_folders` in config/ui.yaml or add paths on **Run Dashboard**.")
    st.stop()

labels = {p.split("/")[-1]: p for p in catalog_paths}

if "input_txt_draft" not in st.session_state:
    st.session_state.input_txt_draft = ""
if "step_a_cmd" not in st.session_state:
    st.session_state.step_a_cmd = format_salloc_command(config)
if "step_b_cmd" not in st.session_state:
    st.session_state.step_b_cmd = format_parallel_command(config)

st.subheader("1. Choose folders (optional starter for input.txt)")
remote_dirs: list[str] = []
if ssh_ok:
    if st.button("Refresh folder list from Perlmutter"):
        st.session_state["remote_run_dirs"] = list_blast_run_dirs(config)
    remote_dirs = st.session_state.get("remote_run_dirs") or []
    if not remote_dirs:
        with st.spinner("Listing run dirs on Perlmutter..."):
            try:
                remote_dirs = list_blast_run_dirs(config)
                st.session_state["remote_run_dirs"] = remote_dirs
            except RemoteError as exc:
                st.warning(f"Could not list remote dirs: {exc}")

options = remote_dirs if remote_dirs else list(labels.values())
default_sel = [p for p in options if p.split("/")[-1] in labels]
selected = st.multiselect(
    "Run folders",
    options=options,
    default=default_sel or options[:1],
    format_func=lambda p: p.split("/")[-1] if "/" in p else p,
)

col_fill, col_load = st.columns(2)
with col_fill:
    if st.button("Fill editor from selected folders"):
        try:
            paths = [normalize_run_path(config, p) for p in selected]
            st.session_state.input_txt_draft = format_input_txt_lines(paths)
            st.rerun()
        except SubmitPathError as exc:
            st.error(str(exc))
with col_load:
    if ssh_ok and st.button("Load input.txt from Perlmutter into editor"):
        try:
            st.session_state.input_txt_draft = read_input_txt(config)
            st.rerun()
        except RemoteError as exc:
            st.error(str(exc))

st.subheader("2. Edit input.txt")
st.caption("One absolute run-directory path per line (trailing `/` is fine). Fix paths here before writing.")
st.text_area(
    "input.txt content",
    height=160,
    key="input_txt_draft",
    label_visibility="collapsed",
    placeholder="/global/cfs/cdirs/.../ML-Tersoff-1_PE/\n/global/cfs/cdirs/.../ML-Tersoff-1_PE_hybrid/",
)

if ssh_ok:
    if st.button("Write edited input.txt to Perlmutter", type="primary"):
        try:
            write_input_txt_content(config, st.session_state.input_txt_draft)
            st.success(f"Wrote {config.input_txt_remote_path}")
        except (RemoteError, SubmitPathError) as exc:
            st.error(str(exc))
else:
    st.error(f"SSH unavailable: {ssh_msg}")

st.subheader("3. Launch on GPU")

with st.expander("Step A settings (salloc)", expanded=True):
    c1, c2, c3 = st.columns(3)
    with c1:
        salloc_nodes = st.number_input("Nodes", min_value=1, max_value=16, value=config.salloc_nodes)
        salloc_time = st.text_input("Time (HH:MM:SS)", value=config.salloc_time)
    with c2:
        salloc_qos = st.text_input("QoS", value=config.salloc_qos)
        salloc_account = st.text_input("Account", value=config.submit_account)
    with c3:
        salloc_ntasks = st.number_input(
            "ntasks-per-node", min_value=1, max_value=128, value=config.salloc_ntasks_per_node
        )
        salloc_gpus_per_task = st.number_input(
            "gpus-per-task", min_value=1, max_value=4, value=config.salloc_gpus_per_task
        )
        salloc_gpus = st.number_input("Total GPUs (--gpus)", min_value=1, max_value=32, value=config.salloc_gpus)

    rebuild_a = st.button("Rebuild Step A from fields above")

st.markdown("**Step A — request interactive GPUs (login node)**")
if rebuild_a:
    st.session_state.step_a_cmd = format_salloc_command(
        config,
        nodes=int(salloc_nodes),
        salloc_time=salloc_time.strip(),
        qos=salloc_qos.strip(),
        ntasks_per_node=int(salloc_ntasks),
        gpus_per_task=int(salloc_gpus_per_task),
        gpus=int(salloc_gpus),
        account=salloc_account.strip(),
    )
    st.rerun()

st.text_area(
    "Step A command",
    height=80,
    key="step_a_cmd",
    label_visibility="collapsed",
)

rebuild_b = st.button("Rebuild Step B from config defaults")
if rebuild_b:
    st.session_state.step_b_cmd = format_parallel_command(config)
    st.rerun()

st.markdown("**Step B — parallel RunBOP.py (compute node)**")
st.text_area(
    "Step B command",
    height=80,
    key="step_b_cmd",
    label_visibility="collapsed",
)

salloc_kw = dict(
    nodes=int(salloc_nodes),
    salloc_time=salloc_time.strip(),
    qos=salloc_qos.strip(),
    ntasks_per_node=int(salloc_ntasks),
    gpus_per_task=int(salloc_gpus_per_task),
    gpus=int(salloc_gpus),
    account=salloc_account.strip(),
)

with st.expander("Preview: dashboard SSH launch command", expanded=False):
    try:
        st.code(
            preview_interactive_launch_command(config, st.session_state.step_b_cmd, **salloc_kw),
            language="bash",
        )
    except SubmitPathError as exc:
        st.caption(str(exc))

st.subheader("4. Submit from dashboard")
confirm_gpu = st.checkbox(
    "I confirm: this starts GPU work on Perlmutter (input.txt must exist on the cluster).",
    key="confirm_gpu_launch",
)
write_then_launch = st.checkbox("Write input.txt from editor immediately before launch", value=True)

col_int, col_batch = st.columns(2)
log_box = st.empty()

with col_int:
    launch_interactive = st.button(
        "Launch interactive (salloc + Step B)",
        type="primary",
        disabled=not (ssh_ok and confirm_gpu),
    )
with col_batch:
    launch_batch = st.button(
        "Submit batch (sbatch)",
        disabled=not (ssh_ok and confirm_gpu),
    )

if launch_interactive and ssh_ok:
    try:
        if write_then_launch:
            write_input_txt_content(config, st.session_state.input_txt_draft)
        lines: list[str] = []
        with st.spinner("Running on Perlmutter (queue wait + RunBOP may take a long time)..."):
            for chunk in run_interactive_launch_stream(
                config, st.session_state.step_b_cmd, **salloc_kw
            ):
                lines.append(chunk)
                tail = "".join(lines)[-12_000:]
                log_box.code(tail or "(waiting for output…)", language=None)
        full = "".join(lines)
        if "error" in full.lower() or "failed" in full.lower():
            st.warning("Launch finished — review log below for errors.")
        else:
            st.success("Launch command completed.")
        with st.expander("Full launch log", expanded=False):
            st.code(full or "(no output)", language=None)
    except (RemoteError, SubmitPathError) as exc:
        st.error(str(exc))

if launch_batch and ssh_ok:
    try:
        if write_then_launch:
            write_input_txt_content(config, st.session_state.input_txt_draft)
        with st.spinner("Submitting sbatch on Perlmutter..."):
            result = run_batch_submit(config, deploy_script=True)
        st.success(f"Submitted batch job **{result.job_id}**")
        st.code(result.raw_output, language=None)
        st.caption("Check **Jobs** page or run `squeue --me` on Perlmutter. Logs: slurm-runBOP-<jobid>.out in blast_root.")
    except (RemoteError, SubmitPathError) as exc:
        st.error(str(exc))

st.caption("Manual fallback: copy Step A/B above into your own SSH session if dashboard launch fails.")

st.divider()
st.subheader("Notes for this search (optional)")
instructions = st.text_area(
    "What should differ in this run?",
    height=100,
    placeholder="e.g. hybrid main1.py CE polymorphs; tighten bounds from best PE trial",
)
bound_pct = st.slider("Default bound tightening (%) if tightening", 5, 25, 10)
use_mcts = st.checkbox("MCTS search (RunBOP.py)", value=True)

if st.button("Save instruction notes") and instructions.strip() and selected:
    try:
        run_path = normalize_run_path(config, selected[0])
    except SubmitPathError:
        run_path = selected[0]
    record = JobInstruction(
        run_folder_path=run_path,
        instructions=instructions.strip(),
        bound_tighten_pct=float(bound_pct),
        use_mcts=use_mcts,
    )
    save_instruction(record)
    st.success("Saved to .cursor/status/job_instructions.json")

pending = load_instruction()
if pending:
    with st.expander("Last saved instruction", expanded=False):
        st.code(plan_summary(pending), language=None)

st.caption("See docs/agenticblast-submit.md for the full workflow.")
