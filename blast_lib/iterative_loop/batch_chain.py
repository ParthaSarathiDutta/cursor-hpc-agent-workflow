"""Build Slurm dependency chains for NERSC-autonomous iterative loop."""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from blast_lib.config_types import REPO_ROOT, UIConfig
from blast_lib.iterative_loop.remote_workflow import RemoteWorkflow, agentic_loop_dir


@dataclass
class CycleSubmitSpec:
    cycle: int
    gpu_dependency: str | None  # afterok:jobid for cycle > 1
    range_gpu_job_var: str  # shell var holding gpu job id for this cycle


def parse_sbatch_parsable(line: str) -> str:
    """First field from sbatch --parsable (jobid or jobid;cluster)."""
    return line.strip().split(";")[0].strip()


def build_cycle_specs(total_cycles: int) -> list[CycleSubmitSpec]:
    specs: list[CycleSubmitSpec] = []
    for i in range(1, total_cycles + 1):
        gpu_dep = f"afterok:${{range{i - 1}}}" if i > 1 else None
        specs.append(
            CycleSubmitSpec(
                cycle=i,
                gpu_dependency=gpu_dep,
                range_gpu_job_var=f"gpu{i}",
            )
        )
    return specs


def render_loop_gpu_slurm(config: UIConfig, *, batch_time: str) -> str:
    path = REPO_ROOT / config.loop_gpu_slurm_script
    text = path.read_text()
    reps = {
        "{{SUBMIT_ACCOUNT}}": config.submit_account,
        "{{BATCH_QOS}}": config.batch_qos,
        "{{BATCH_TIME}}": batch_time,
        "{{BATCH_NODES}}": str(config.batch_nodes),
        "{{BATCH_NTASKS_PER_NODE}}": str(config.batch_ntasks_per_node),
        "{{BATCH_GPUS_PER_TASK}}": str(config.batch_gpus_per_task),
        "{{BATCH_GPUS}}": str(config.batch_gpus),
        "{{BLAST_ROOT}}": config.blast_root.rstrip("/"),
        "{{BLAST_PYTHON}}": config.blast_python,
        "{{INPUT_TXT_NAME}}": config.input_txt_name,
        "{{LOOP_GPU_SCRIPT}}": f"{config.blast_root.rstrip('/')}/scripts/agentic_loop_gpu.py",
    }
    for k, v in reps.items():
        text = text.replace(k, v)
    return text


def render_loop_range_slurm(config: UIConfig) -> str:
    path = REPO_ROOT / config.loop_range_slurm_script
    text = path.read_text()
    reps = {
        "{{SUBMIT_ACCOUNT}}": config.submit_account,
        "{{RANGE_QOS}}": config.range_qos,
        "{{RANGE_TIME}}": config.range_time,
        "{{BLAST_PYTHON}}": config.blast_python,
        "{{LOOP_RANGE_SCRIPT}}": f"{config.blast_root.rstrip('/')}/scripts/agentic_loop_range.py",
    }
    for k, v in reps.items():
        text = text.replace(k, v)
    return text


def render_submit_chain_bash(config: UIConfig, wf: RemoteWorkflow) -> str:
    """Bash run once on Perlmutter login to sbatch the full dependency chain."""
    run = wf.run_folder.rstrip("/")
    loop_dir = agentic_loop_dir(run).as_posix()
    log_dir = f"{loop_dir}/logs"
    blast_root = config.blast_root.rstrip("/")
    gpu_slurm = f"{blast_root}/{config.loop_gpu_slurm_remote_name}"
    range_slurm = f"{blast_root}/{config.loop_range_slurm_remote_name}"
    walltime = wf.walltime
    total = wf.total_cycles
    py = config.blast_python
    cli = f"{blast_root}/scripts/agentic_loop_workflow_cli.py"

    lines = [
        "#!/bin/bash",
        "set -euo pipefail",
        f'RUN_FOLDER={shlex.quote(run)}',
        f'BLAST_ROOT={shlex.quote(blast_root)}',
        f'LOG_DIR={shlex.quote(log_dir)}',
        f'WORKFLOW_DIR={shlex.quote(loop_dir)}',
        'mkdir -p "$LOG_DIR"',
        "",
    ]

    for i in range(1, total + 1):
        gpu_dep_args = ""
        if i > 1:
            gpu_dep_args = f'--dependency=afterok:${{range{i - 1}}}'
        lines.extend(
            [
                f'gpu{i}=$(sbatch --parsable {gpu_dep_args} \\',
                f'  --job-name=agentic_loop_gpu_c{i} \\',
                f'  --output="$LOG_DIR/gpu_c{i}_%j.out" \\',
                f'  --error="$LOG_DIR/gpu_c{i}_%j.err" \\',
                f'  --export=ALL,AGENTIC_CYCLE={i},RUN_FOLDER="$RUN_FOLDER",WORKFLOW_DIR="$WORKFLOW_DIR",BLAST_ROOT="$BLAST_ROOT",BLAST_PYTHON={shlex.quote(py)},INPUT_TXT={shlex.quote(config.input_txt_name)} \\',
                f'  --chdir="$BLAST_ROOT" \\',
                f"  {shlex.quote(gpu_slurm)})",
                f'gpu{i}=${{gpu{i}%%;*}}',
                f'echo "Submitted GPU cycle {i}: $gpu{i}"',
                f'{shlex.quote(py)} {shlex.quote(cli)} set-gpu-job "$RUN_FOLDER" {i} "$gpu{i}"',
                "",
                f'range{i}=$(sbatch --parsable --dependency=afterany:$gpu{i} \\',
                f'  --job-name=agentic_loop_range_c{i} \\',
                f'  --output="$LOG_DIR/range_c{i}_%j.out" \\',
                f'  --error="$LOG_DIR/range_c{i}_%j.err" \\',
                f'  --export=ALL,AGENTIC_CYCLE={i},GPU_JOB_ID=$gpu{i},RUN_FOLDER="$RUN_FOLDER",WORKFLOW_DIR="$WORKFLOW_DIR",BLAST_PYTHON={shlex.quote(py)},WALLTIME={shlex.quote(walltime)},TOTAL_CYCLES={total} \\',
                f'  --chdir="$BLAST_ROOT" \\',
                f"  {shlex.quote(range_slurm)})",
                f'range{i}=${{range{i}%%;*}}',
                f'echo "Submitted Range cycle {i}: $range{i} (afterany gpu $gpu{i})"',
                f'{shlex.quote(py)} {shlex.quote(cli)} set-range-job "$RUN_FOLDER" {i} "$range{i}"',
                "",
            ]
        )

    lines.append('echo "Dependency chain submitted."')
    return "\n".join(lines) + "\n"
