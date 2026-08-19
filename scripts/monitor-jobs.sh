#!/usr/bin/env bash
# Monitor Slurm jobs and tail BLAST logs from Perlmutter login node.
# Usage: ./scripts/monitor-jobs.sh [job_id]

set -euo pipefail

JOB_ID="${1:-}"

echo "==> Your jobs (squeue --me)"
squeue --me || true

if [[ -n "${JOB_ID}" ]]; then
  echo
  echo "==> Tailing logs for job ${JOB_ID}"
  OUT="logs/blast_${JOB_ID}.out"
  ERR="logs/blast_${JOB_ID}.err"
  if [[ -f "${OUT}" ]]; then
    tail -f "${OUT}"
  elif [[ -f "${ERR}" ]]; then
    tail -f "${ERR}"
  else
    echo "No log files found at ${OUT} or ${ERR}"
    echo "Also check default slurm output: slurm-${JOB_ID}.out"
    ls -la logs/ slurm-*.out 2>/dev/null || true
  fi
else
  echo
  echo "Recent log files:"
  ls -lt logs/*.out 2>/dev/null | head -5 || echo "(no logs/ yet)"
  echo
  echo "Tip: ./scripts/monitor-jobs.sh <job_id>"
fi
