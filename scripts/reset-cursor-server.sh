#!/usr/bin/env bash
# Reset Cursor remote server on Perlmutter if install/connect hangs.
# Run via normal SSH: ssh perlmutter 'bash -s' < scripts/reset-cursor-server.sh

set -euo pipefail

echo "Stopping cursor-server processes..."
pkill -f cursor-server 2>/dev/null || true

echo "Removing ~/.cursor-server (may take a while on NFS)..."
rm -rf "${HOME}/.cursor-server"

echo "Done. Reconnect from Cursor: Remote-SSH -> perlmutter"
