#!/usr/bin/env bash
# Start the local BLAST dashboard (Streamlit on http://127.0.0.1:8501).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

if [[ ! -d .venv ]]; then
  echo "Creating virtualenv in .venv ..."
  python3 -m venv .venv
  .venv/bin/pip install -r requirements-ui.txt
fi

# shellcheck disable=SC1091
source .venv/bin/activate

URL="http://127.0.0.1:8501"

# Stop any stale instance on the same port.
if lsof -ti :8501 >/dev/null 2>&1; then
  echo "Stopping existing process on port 8501 ..."
  lsof -ti :8501 | xargs kill 2>/dev/null || true
  sleep 1
fi

echo "Starting dashboard at ${URL}"
echo ""
echo "IMPORTANT: Open this URL in Safari or Chrome — NOT Cursor's built-in browser."
echo "           Streamlit requires WebSockets; Cursor preview often fails."
echo ""

# Start server in background, open external browser, wait for server.
streamlit run ui/app.py \
  --server.address 127.0.0.1 \
  --server.port 8501 \
  --server.headless true \
  "$@" &
SERVER_PID=$!

for _ in $(seq 1 20); do
  if curl -sf "${URL}/_stcore/health" >/dev/null 2>&1; then
    echo "Dashboard is up."
    if [[ "$(uname)" == "Darwin" ]]; then
      open "${URL}"
    fi
    echo "Press Ctrl+C to stop."
    wait "${SERVER_PID}"
    exit 0
  fi
  sleep 0.5
done

echo "ERROR: Dashboard failed to start. Last log lines:"
kill "${SERVER_PID}" 2>/dev/null || true
exit 1
