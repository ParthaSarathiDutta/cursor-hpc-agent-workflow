#!/bin/bash
#SBATCH -A {{SUBMIT_ACCOUNT}}
#SBATCH -C gpu
#SBATCH -q {{BATCH_QOS}}
#SBATCH -t {{BATCH_TIME}}
#SBATCH -N {{BATCH_NODES}}
#SBATCH --ntasks-per-node={{BATCH_NTASKS_PER_NODE}}
#SBATCH --gpus-per-task={{BATCH_GPUS_PER_TASK}}
#SBATCH --gpus={{BATCH_GPUS}}

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-{{BLAST_ROOT}}}"

: "${AGENTIC_CYCLE:?}"
: "${RUN_FOLDER:?}"
: "${BLAST_ROOT:?}"
: "${BLAST_PYTHON:?}"
: "${INPUT_TXT:?}"

export WORKFLOW_DIR="${WORKFLOW_DIR:-${RUN_FOLDER}/.agentic_loop}"

"{{BLAST_PYTHON}}" "{{LOOP_GPU_SCRIPT}}"
