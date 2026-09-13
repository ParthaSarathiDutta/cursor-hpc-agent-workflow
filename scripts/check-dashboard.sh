#!/usr/bin/env bash
# Verify dashboard prerequisites; auto-start server if down.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
URL="http://127.0.0.1:8501"
AUTO_START=1
for arg in "$@"; do
  if [[ "${arg}" == "--no-start" ]]; then
    AUTO_START=0
  fi
done

echo "==> Python venv"
if [[ -d .venv ]]; then
  echo "OK  .venv exists"
  .venv/bin/python -c "import streamlit, yaml, plotly, pandas; print('OK  packages installed')"
else
  echo "FAIL  .venv missing — run: python3 -m venv .venv && .venv/bin/pip install -r requirements-ui.txt"
  exit 1
fi

echo ""
echo "==> Gemini API key"
if .venv/bin/python -c "from blast_lib.gemini_client import llm_available; import sys; sys.exit(0 if llm_available() else 1)"; then
  echo "OK  GOOGLE_API_KEY / GEMINI_API_KEY loaded from .env"
else
  echo "WARN  No Gemini key — Agent Chat disabled (add keys to .env)"
fi

echo ""
echo "==> Dashboard server"
if curl -sf "${URL}/_stcore/health" >/dev/null 2>&1; then
  echo "OK  Dashboard responding at ${URL}"
else
  echo "FAIL  Nothing listening at ${URL}"
  if [[ "${AUTO_START}" -eq 1 ]]; then
    if launchctl print "gui/$(id -u)/com.blast.dashboard" >/dev/null 2>&1; then
      echo "      LaunchAgent installed — kickstarting watchdog ..."
      launchctl kickstart -k "gui/$(id -u)/com.blast.dashboard" 2>/dev/null || true
      sleep 3
    else
      echo "      Auto-starting (tip: ./scripts/install-dashboard-agent.sh for persistent hosting) ..."
      ./scripts/dashboard-dev.sh start
    fi
    if curl -sf "${URL}/_stcore/health" >/dev/null 2>&1; then
      echo "OK  Dashboard now responding at ${URL}"
    else
      echo "FAIL  Auto-start failed — see .cursor/dashboard/streamlit.log"
      exit 1
    fi
  else
    echo "      Start with: ./scripts/dashboard-dev.sh start"
    exit 1
  fi
fi

echo ""
echo "==> Perlmutter SSH (optional)"
if ssh -o ConnectTimeout=5 -o BatchMode=yes perlmutter echo ok 2>/dev/null; then
  echo "OK  ssh perlmutter"
else
  echo "WARN  ssh perlmutter failed — UI works, but Sync/Jobs need SSH"
  echo "      Run: cd ${ROOT} && ./scripts/setup-sshproxy.sh"
fi

echo ""
echo "All checks passed. Open ${URL} in Safari or Chrome (not Cursor's built-in browser)."
