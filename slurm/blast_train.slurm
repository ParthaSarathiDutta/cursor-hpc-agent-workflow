#!/bin/bash
#SBATCH -A YOUR_GPU_ACCOUNT_g
#SBATCH -C gpu
#SBATCH -q regular
#SBATCH -t 04:00:00
#SBATCH -N 1
#SBATCH --gpus-per-node=4
#SBATCH -J blast_train
#SBATCH -o logs/blast_%j.out
#SBATCH -e logs/blast_%j.err

# BLAST GPU training job for NERSC Perlmutter
# Submit: sbatch slurm/blast_train.slurm
# Monitor: squeue --me && tail -f logs/blast_<jobid>.out

set -euo pipefail

# --- Adjust to your environment ---
# module load python
# module load pytorch
# source activate blast_env

cd "${SLURM_SUBMIT_DIR}"

# Use scratch for temp/cache to avoid HOME quota issues
export TMPDIR="${SCRATCH:-/tmp}/${USER}/tmp"
mkdir -p "${TMPDIR}" logs

# Replace with your BLAST training command
# python scripts/train.py configs/your_config.yaml
echo "BLAST training placeholder — replace with your train command"
echo "Job ID: ${SLURM_JOB_ID} on $(hostname)"
nvidia-smi || true
