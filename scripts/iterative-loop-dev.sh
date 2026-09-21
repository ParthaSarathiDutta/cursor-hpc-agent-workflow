#!/usr/bin/env bash
# Background runner for autonomous iterative BLAST loop.
# Usage: ./scripts/iterative-loop-dev.sh {start|stop|status|once|logs}
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

RUN_DIR="${ROOT}/.cursor/iterative_loop"
PID_FILE="${RUN_DIR}/runner.pid"
LOG_FILE="${RUN_DIR}/runner.log"

mkdir -p "${RUN_DIR}"

_venv_python() {
  if [[ -x "${ROOT}/.venv/bin/python" ]]; then
    echo "${ROOT}/.venv/bin/python"
  else
    echo python3
  fi
}

cmd_start() {
  if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    echo "Iterative loop runner already running (pid $(cat "${PID_FILE}"))."
    return 0
  fi
  PY="$(_venv_python)"
  echo "Starting iterative loop runner (background)."
  echo "Logs: ${LOG_FILE}"
  nohup "${PY}" -m blast_lib.iterative_loop.runner >>"${LOG_FILE}" 2>&1 &
  echo $! >"${PID_FILE}"
  echo "Runner pid $(cat "${PID_FILE}")"
}

cmd_stop() {
  if [[ -f "${PID_FILE}" ]]; then
    kill "$(cat "${PID_FILE}")" 2>/dev/null || true
    rm -f "${PID_FILE}"
  fi
  pkill -f "blast_lib.iterative_loop.runner" 2>/dev/null || true
  echo "Runner stopped."
}

cmd_status() {
  if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    echo "RUNNING  pid $(cat "${PID_FILE}")"
  else
    echo "STOPPED"
  fi
}

cmd_once() {
  PY="$(_venv_python)"
  "${PY}" -m blast_lib.iterative_loop.runner --once
}

cmd_logs() {
  tail -f "${LOG_FILE}"
}

case "${1:-status}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  once) cmd_once ;;
  logs) cmd_logs ;;
  *)
    echo "Usage: $0 {start|stop|status|once|logs}"
    exit 1
    ;;
esac
