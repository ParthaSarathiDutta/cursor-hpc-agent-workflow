#!/usr/bin/env bash
set -euo pipefail

LABEL="com.blast.dashboard"
PLIST_DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
rm -f "${PLIST_DEST}"
"$(cd "$(dirname "$0")/.." && pwd)/scripts/dashboard-dev.sh" stop 2>/dev/null || true

echo "Removed LaunchAgent ${LABEL}"
