#!/bin/bash
#SBATCH -A {{SUBMIT_ACCOUNT}}
#SBATCH -q {{RANGE_QOS}}
#SBATCH -t {{RANGE_TIME}}
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH -C cpu

set -euo pipefail

: "${AGENTIC_CYCLE:?}"
: "${GPU_JOB_ID:?}"
: "${RUN_FOLDER:?}"
: "${BLAST_PYTHON:?}"
: "${WALLTIME:?}"
: "${TOTAL_CYCLES:?}"

export WORKFLOW_DIR="${WORKFLOW_DIR:-${RUN_FOLDER}/.agentic_loop}"

"{{BLAST_PYTHON}}" "{{LOOP_RANGE_SCRIPT}}"
