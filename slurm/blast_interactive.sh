#!/usr/bin/env bash
# Request an interactive GPU allocation on Perlmutter.
# Run from Cursor integrated terminal (login node only — do not run heavy compute here).
#
# Usage:
#   export NERSC_GPU_ACCOUNT=m1234_g   # set your GPU account
#   ./slurm/blast_interactive.sh

set -euo pipefail

ACCOUNT="${NERSC_GPU_ACCOUNT:-YOUR_GPU_ACCOUNT_g}"
TIME="${NERSC_INTERACTIVE_TIME:-01:00:00}"
GPUS="${NERSC_INTERACTIVE_GPUS:-4}"

echo "Requesting interactive GPU node (account=${ACCOUNT}, time=${TIME}, gpus=${GPUS})"
salloc \
  --nodes 1 \
  --qos interactive \
  --time "${TIME}" \
  --constraint gpu \
  --gpus "${GPUS}" \
  --account "${ACCOUNT}"
