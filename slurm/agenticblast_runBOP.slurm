#!/bin/bash
#SBATCH -A {{SUBMIT_ACCOUNT}}
#SBATCH -C gpu
#SBATCH -q {{BATCH_QOS}}
#SBATCH -t {{BATCH_TIME}}
#SBATCH -N {{BATCH_NODES}}
#SBATCH --ntasks-per-node={{BATCH_NTASKS_PER_NODE}}
#SBATCH --gpus-per-task={{BATCH_GPUS_PER_TASK}}
#SBATCH --gpus={{BATCH_GPUS}}
#SBATCH -J agenticblast_runBOP
#SBATCH -o slurm-runBOP-%j.out
#SBATCH -e slurm-runBOP-%j.err

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"

INPUT="{{INPUT_TXT_NAME}}"
PY="{{BLAST_PYTHON}}"
inner='cd {}; unlink tmp; '"${PY}"' {}RunBOP.py'

echo "Job ${SLURM_JOB_ID} on $(hostname)"
echo "Submit dir: ${SLURM_SUBMIT_DIR}"
cat "${INPUT}" | parallel "${inner}"
