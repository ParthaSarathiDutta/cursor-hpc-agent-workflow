#!/bin/bash -l
#SBATCH -A {{ORCHESTRATOR_ACCOUNT}}
#SBATCH -q cron
#SBATCH -C cron
#SBATCH -t {{ORCHESTRATOR_WALLTIME}}
#SBATCH -J agentic_loop_orch
#SBATCH -o {{LOG_DIR}}/orch-%j.out

set -euo pipefail

: "${RUN_FOLDER:?RUN_FOLDER required}"
: "${BLAST_ROOT:?BLAST_ROOT required}"
: "${BLAST_PYTHON:?BLAST_PYTHON required}"

export RUN_FOLDER BLAST_ROOT BLAST_PYTHON
cd "${BLAST_ROOT}"

exec "${BLAST_PYTHON}" "${BLAST_ROOT}/scripts/agentic_loop_orchestrator.py" "${RUN_FOLDER}"
