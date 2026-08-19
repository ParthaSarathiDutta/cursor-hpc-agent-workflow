#!/bin/bash
#SBATCH -A YOUR_GPU_ACCOUNT_g
#SBATCH -C gpu
#SBATCH -q regular
#SBATCH -t 01:00:00
#SBATCH -N 1
#SBATCH --gpus-per-node=1
#SBATCH -J blast_validate
#SBATCH -o logs/validate_%j.out
#SBATCH -e logs/validate_%j.err

set -euo pipefail

cd "${SLURM_SUBMIT_DIR}"
export TMPDIR="${SCRATCH:-/tmp}/${USER}/tmp"
mkdir -p "${TMPDIR}" logs

# Replace with your BLAST validation command
# python scripts/validate.py configs/your_config.yaml --checkpoint results/latest.pt
echo "BLAST validation placeholder — replace with your validate command"
echo "Job ID: ${SLURM_JOB_ID} on $(hostname)"
