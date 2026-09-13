#!/usr/bin/env bash
# Watchdog loop — keeps Streamlit alive. Used by macOS LaunchAgent or manual run.
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

URL="http://127.0.0.1:8501"
PORT=8501
LOG_FILE="${ROOT}/.cursor/dashboard/watchdog.log"
STREAMLIT="${ROOT}/.venv/bin/streamlit"
mkdir -p "${ROOT}/.cursor/dashboard"

_health() {
  curl -sf "${URL}/_stcore/health" >/dev/null 2>&1
}

_log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "${LOG_FILE}"
}

while true; do
  if _health; then
    sleep 5
    continue
  fi

  if lsof -ti :"${PORT}" >/dev/null 2>&1; then
    _log "port ${PORT} busy but unhealthy — clearing"
    lsof -ti :"${PORT}" | xargs kill 2>/dev/null || true
    sleep 2
  fi

  _log "starting streamlit on :${PORT}"
  "${STREAMLIT}" run ui/app.py \
    --server.address 127.0.0.1 \
    --server.port "${PORT}" \
    --server.headless true \
    >>"${ROOT}/.cursor/dashboard/streamlit.log" 2>&1 &
  ST_PID=$!

  for _ in $(seq 1 30); do
    if _health; then
      _log "streamlit up (pid ${ST_PID})"
      break
    fi
    sleep 0.5
  done

  wait "${ST_PID}" || true
  _log "streamlit exited (pid ${ST_PID}) — restart in 3s"
  sleep 3
done
