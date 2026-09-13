#!/usr/bin/env bash
# Persistent local dashboard — start once, auto-reloads on file save.
# Usage: ./scripts/dashboard-dev.sh {start|stop|status|restart|ensure|logs|open}
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi

RUN_DIR="${ROOT}/.cursor/dashboard"
PID_FILE="${RUN_DIR}/streamlit.pid"
LOG_FILE="${RUN_DIR}/streamlit.log"
URL="http://127.0.0.1:8501"
PORT=8501

mkdir -p "${RUN_DIR}"

_python_for_venv() {
  for candidate in python3.12 python3.11 python3; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      echo "${candidate}"
      return 0
    fi
  done
  echo "python3"
}

_venv() {
  PY="$(_python_for_venv)"
  if [[ -d .venv ]]; then
    vpy="$(.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "?")"
    if [[ "${vpy}" == "3.14" ]]; then
      echo "Recreating .venv (Streamlit unstable on Python 3.14; using ${PY}) ..."
      rm -rf .venv
    fi
  fi
  if [[ ! -d .venv ]]; then
    echo "Creating .venv with ${PY} ..."
    "${PY}" -m venv .venv
    .venv/bin/pip install -r requirements-ui.txt
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
}

_health() {
  curl -sf "${URL}/_stcore/health" >/dev/null 2>&1
}

_wait_health() {
  for _ in $(seq 1 30); do
    if _health; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

_clear_port() {
  if lsof -ti :"${PORT}" >/dev/null 2>&1; then
    echo "Stopping stale process on port ${PORT} ..."
    lsof -ti :"${PORT}" | xargs kill 2>/dev/null || true
    sleep 1
  fi
}

_launchagent_loaded() {
  launchctl print "gui/$(id -u)/com.blast.dashboard" >/dev/null 2>&1
}

cmd_start() {
  _venv
  if _launchagent_loaded; then
    echo "LaunchAgent installed — use: launchctl kickstart -k gui/\$(id -u)/com.blast.dashboard"
    if _health; then
      echo "Dashboard already running at ${URL}"
      return 0
    fi
    echo "Waiting for LaunchAgent watchdog ..."
    _wait_health && echo "Dashboard is up at ${URL}" && return 0
  fi

  if _health; then
    pid="?"
    [[ -f "${PID_FILE}" ]] && pid="$(cat "${PID_FILE}")"
    echo "Dashboard already running at ${URL} (pid ${pid})"
    return 0
  fi

  _clear_port
  pkill -f "dashboard-watchdog.sh" 2>/dev/null || true
  pkill -f "dashboard-supervisor.sh" 2>/dev/null || true

  echo "Starting dashboard (background) at ${URL}"
  echo "Logs: ${LOG_FILE}"
  nohup .venv/bin/streamlit run ui/app.py \
    --server.address 127.0.0.1 \
    --server.port "${PORT}" \
    --server.headless true \
    >>"${LOG_FILE}" 2>&1 < /dev/null &
  ST_PID=$!
  disown -h "${ST_PID}" 2>/dev/null || disown "${ST_PID}" 2>/dev/null || true
  echo "${ST_PID}" >"${PID_FILE}"

  if _wait_health; then
    echo "Dashboard is up (pid $(cat "${PID_FILE}"))."
    echo ""
    echo "  URL: ${URL}"
    echo "  Open Safari or Chrome — not Cursor's built-in browser."
    echo "  Logs: ./scripts/dashboard-dev.sh logs"
    return 0
  fi

  echo "ERROR: dashboard did not start. Last log lines:"
  tail -20 "${LOG_FILE}" || true
  cmd_stop
  exit 1
}

cmd_stop() {
  if [[ -f "${PID_FILE}" ]]; then
    kill "$(cat "${PID_FILE}")" 2>/dev/null || true
    rm -f "${PID_FILE}"
  fi
  pkill -f "dashboard-supervisor.sh" 2>/dev/null || true
  pkill -f "streamlit run ui/app.py" 2>/dev/null || true
  _clear_port
  echo "Dashboard stopped."
}

cmd_status() {
  if _health; then
    pid="?"
    [[ -f "${PID_FILE}" ]] && pid="$(cat "${PID_FILE}")"
    echo "RUNNING  ${URL}  (pid ${pid})"
  else
    echo "STOPPED  ${URL}"
  fi
}

cmd_restart() {
  cmd_stop
  sleep 1
  cmd_start
}

cmd_ensure() {
  if _health; then
    cmd_status
    return 0
  fi
  if lsof -ti :"${PORT}" >/dev/null 2>&1; then
    echo "Port ${PORT} busy — waiting for Streamlit health ..."
    if _wait_health; then
      cmd_status
      return 0
    fi
    echo "Process on ${PORT} not healthy — clearing and restarting ..."
    _clear_port
  fi
  echo "Dashboard not reachable — starting ..."
  cmd_start
}

cmd_logs() {
  tail -f "${LOG_FILE}"
}

cmd_open() {
  if [[ "$(uname)" == "Darwin" ]]; then
    open "${URL}"
  else
    echo "${URL}"
  fi
}

case "${1:-start}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  restart) cmd_restart ;;
  ensure) cmd_ensure ;;
  logs) cmd_logs ;;
  open) cmd_open ;;
  *)
    echo "Usage: $0 {start|stop|status|restart|ensure|logs|open}"
    exit 1
    ;;
esac
