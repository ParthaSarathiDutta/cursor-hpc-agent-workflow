#!/usr/bin/env bash
# Start the local dashboard (background daemon — survives terminal/Cursor task exit).
# Open Safari/Chrome at http://127.0.0.1:8501
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Prefer LaunchAgent if installed; otherwise one-shot background start.
if launchctl print "gui/$(id -u)/com.blast.dashboard" >/dev/null 2>&1; then
  launchctl kickstart -k "gui/$(id -u)/com.blast.dashboard" 2>/dev/null || true
  sleep 2
else
  "${ROOT}/scripts/dashboard-dev.sh" start
fi
"${ROOT}/scripts/check-dashboard.sh"
"${ROOT}/scripts/dashboard-dev.sh" open
