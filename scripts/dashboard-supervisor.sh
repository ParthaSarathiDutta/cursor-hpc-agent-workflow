#!/usr/bin/env bash
# Keeps Streamlit running; restarts on crash. Started by dashboard-dev.sh.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi

PORT=8501
STREAMLIT="${ROOT}/.venv/bin/streamlit"
ST_PID=""

_stop_streamlit() {
  [[ -n "${ST_PID}" ]] && kill "${ST_PID}" 2>/dev/null || true
  ST_PID=""
}

# Only clean up streamlit on intentional shutdown — not on every shell exit path.
trap '_stop_streamlit; exit 0' INT TERM

while true; do
  echo "$(date '+%Y-%m-%d %H:%M:%S') supervisor: starting streamlit on :${PORT}"
  if lsof -ti :"${PORT}" >/dev/null 2>&1; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') supervisor: port ${PORT} busy — clearing stale holder"
    lsof -ti :"${PORT}" | xargs kill 2>/dev/null || true
    sleep 1
  fi

  "${STREAMLIT}" run ui/app.py \
    --server.address 127.0.0.1 \
    --server.port "${PORT}" \
    --server.headless true &
  ST_PID=$!
  wait "${ST_PID}" || true
  _stop_streamlit
  echo "$(date '+%Y-%m-%d %H:%M:%S') supervisor: streamlit exited — restart in 2s"
  sleep 2
done
