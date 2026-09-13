#!/usr/bin/env bash
# Install a macOS LaunchAgent so the BLAST dashboard stays running (survives Cursor/terminal exit).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.blast.dashboard"
PLIST_DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
WATCHDOG="${ROOT}/scripts/dashboard-watchdog.sh"

chmod +x "${WATCHDOG}"
mkdir -p "${HOME}/Library/LaunchAgents" "${ROOT}/.cursor/dashboard"

cat >"${PLIST_DEST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${WATCHDOG}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${ROOT}/.cursor/dashboard/launchagent.out.log</string>
  <key>StandardErrorPath</key>
  <string>${ROOT}/.cursor/dashboard/launchagent.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key>
    <string>${ROOT}</string>
  </dict>
</dict>
</plist>
EOF

# Stop any manual dashboard first
"${ROOT}/scripts/dashboard-dev.sh" stop 2>/dev/null || true

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "${PLIST_DEST}"
launchctl enable "gui/$(id -u)/${LABEL}"
launchctl kickstart -k "gui/$(id -u)/${LABEL}"

echo "Installed LaunchAgent: ${PLIST_DEST}"
echo "Dashboard URL: http://127.0.0.1:8501"
echo ""
echo "Commands:"
echo "  ./scripts/check-dashboard.sh          # verify"
echo "  launchctl kickstart -k gui/\$(id -u)/${LABEL}   # restart"
echo "  ./scripts/uninstall-dashboard-agent.sh  # remove"
