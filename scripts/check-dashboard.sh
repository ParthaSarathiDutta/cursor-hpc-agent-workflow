#!/usr/bin/env bash
# Verify dashboard prerequisites and whether the server is reachable.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
URL="http://127.0.0.1:8501"

echo "==> Python venv"
if [[ -d .venv ]]; then
  echo "OK  .venv exists"
  .venv/bin/python -c "import streamlit, yaml, plotly, pandas; print('OK  packages installed')"
else
  echo "FAIL  .venv missing — run: python3 -m venv .venv && .venv/bin/pip install -r requirements-ui.txt"
  exit 1
fi

echo ""
echo "==> Dashboard server"
if curl -sf "${URL}/_stcore/health" >/dev/null 2>&1; then
  echo "OK  Dashboard responding at ${URL}"
else
  echo "FAIL  Nothing listening at ${URL}"
  echo "      Start with: ./scripts/run-dashboard.sh"
  exit 1
fi

echo ""
echo "==> Perlmutter SSH (optional)"
if ssh -o ConnectTimeout=5 -o BatchMode=yes perlmutter echo ok 2>/dev/null; then
  echo "OK  ssh perlmutter"
else
  echo "WARN  ssh perlmutter failed — UI works, but Sync/Jobs need SSH"
  echo "      Run: ./scripts/setup-sshproxy.sh"
fi

echo ""
echo "All checks passed. Open ${URL} in Safari or Chrome."
