#!/usr/bin/env bash
# Check HOME quota on Perlmutter — exceeding quota blocks Cursor Remote SSH.
# Run on Perlmutter login node: bash scripts/check-home-quota.sh

set -euo pipefail

echo "==> HOME directory: ${HOME}"
echo

if command -v lfs >/dev/null 2>&1; then
  echo "==> User quota (lfs quota -u ${USER} ${HOME})"
  lfs quota -u "${USER}" "${HOME}" 2>/dev/null || lfs quota -g "$(id -gn)" "${HOME}" 2>/dev/null || true
else
  echo "lfs not available; try: quota -s"
  quota -s 2>/dev/null || true
fi

echo
echo "==> Large items in HOME (top 10)"
du -sh "${HOME}"/.* "${HOME}"/* 2>/dev/null | sort -hr | head -10 || true

echo
echo "==> Cursor server footprint"
du -sh "${HOME}/.cursor-server" 2>/dev/null || echo "(no .cursor-server yet)"

echo
echo "If near quota:"
echo "  - Move datasets/envs to \$SCRATCH"
echo "  - rm -rf ~/.cursor-server (reinstalls on next Cursor connect)"
echo "  - Clean old logs in ~/logs or slurm-*.out"
