#!/usr/bin/env bash
# Verify SSH and Perlmutter environment after setup.
set -euo pipefail

HOST="${1:-perlmutter}"

echo "==> Testing SSH to ${HOST}"
if ! ssh -o BatchMode=yes -o ConnectTimeout=15 "${HOST}" "hostname && whoami"; then
  echo
  echo "SSH failed. Common fixes:"
  echo "  1. Run: ./scripts/setup-sshproxy.sh   (needs Iris password + OTP)"
  echo "  2. Check NERSC status: https://www.nersc.gov/users/status"
  echo "  3. Ensure ~/.ssh/nersc exists and is less than 24h old"
  exit 1
fi

echo
echo "==> Perlmutter environment"
ssh "${HOST}" bash -s <<'REMOTE'
set -euo pipefail
echo "HOSTNAME=$(hostname)"
echo "USER=${USER}"
echo "HOME=${HOME}"
echo "SCRATCH=${SCRATCH:-not set}"
echo "PSCRATCH=${PSCRATCH:-not set}"
echo
echo "Slurm accounts (if any):"
env | grep -E '^(SALLOC|SBATCH|SLURM)_ACCOUNT' || true
echo
echo "HOME quota:"
if command -v lfs >/dev/null 2>&1; then
  lfs quota -u "${USER}" "${HOME}" 2>/dev/null || echo "(quota command unavailable)"
else
  echo "(lfs not available on login node)"
fi
echo
echo "BLAST / conda hints:"
module avail blast 2>&1 | head -5 || true
conda env list 2>/dev/null | head -10 || echo "(conda not in default PATH)"
REMOTE

echo
echo "SUCCESS: Perlmutter connection verified."
