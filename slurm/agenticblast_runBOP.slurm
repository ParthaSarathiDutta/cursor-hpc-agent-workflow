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
BLAST_ROOT="${SLURM_SUBMIT_DIR}"
SHIM="${BLAST_ROOT}/.env_shim"
CUDART="/global/cfs/cdirs/m1917/blast_ff/bin/miniconda3/lib/libcudart.so.11.0"
MPICH_SHIM="/usr/lib/shifter/mpich-2.2"
mkdir -p "${SHIM}"
ln -sf "${CUDART}" "${SHIM}/libcudart.so.11.0"
export LD_LIBRARY_PATH="${SHIM}:${MPICH_SHIM}:${LD_LIBRARY_PATH:-}"
inner='export LD_LIBRARY_PATH="'"${SHIM}:${MPICH_SHIM}"':${LD_LIBRARY_PATH:-}; cd {}; rm -rf tmp; '"${PY}"' {}RunBOP.py'

echo "Job ${SLURM_JOB_ID} on $(hostname)"
echo "Submit dir: ${SLURM_SUBMIT_DIR}"
echo "LD_LIBRARY_PATH=${LD_LIBRARY_PATH}"
cat "${INPUT}" | parallel "${inner}"
