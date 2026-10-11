#!/usr/bin/env bash
# Wait for current interactive Slurm job to finish, finish cycle in controller, run remaining cycles.
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
PY="${ROOT}/.venv/bin/python"
JOB_ID="${1:-}"
LOG="${ROOT}/.cursor/iterative_loop/recover.log"
mkdir -p "${ROOT}/.cursor/iterative_loop"
exec >>"${LOG}" 2>&1
echo "=== recover-and-continue $(date -u +%Y-%m-%dT%H:%M:%SZ) job=${JOB_ID} ==="

RECOVER_JOB="${JOB_ID}" "${PY}" -u -c "
import os
import subprocess
import time

from blast_lib.config import load_config
from blast_lib.env import load_repo_dotenv
from blast_lib.iterative_loop.controller import IterativeRunController
from blast_lib.iterative_loop.state import Phase, load_state, save_state
from blast_lib.iterative_loop.submit_agent import InteractiveSubmitResult

load_repo_dotenv()
config = load_config()
state = load_state(config)
job = os.environ.get('RECOVER_JOB') or state.active_job_id or ''

host = config.ssh_host
if job:
    print(f'Waiting for Slurm job {job} to leave queue…')
    while True:
        out = subprocess.run(
            ['ssh', host, f'squeue -h -j {job} 2>/dev/null || true'],
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout.strip()
        if not out:
            break
        time.sleep(30)
else:
    print('No job id — waiting until user has no interactive jobs…')
    while True:
        out = subprocess.run(
            ['ssh', host, 'squeue -h -u \$USER -n interactive 2>/dev/null || true'],
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout.strip()
        if not out:
            break
        time.sleep(30)

print('Allocation ended. Finishing cycle in controller…')
state = load_state(config)
state.interactive_launch_started = False
state.phase = Phase.RUNNING_INTERACTIVE
if job and not state.active_job_id:
    state.active_job_id = job
save_state(config, state)

controller = IterativeRunController(config)
result = InteractiveSubmitResult(returncode=0, log='', allocation_job_id=job or state.active_job_id)
controller.finish_interactive_cycle(result)
state = load_state(config)
print(f'After finish: phase={state.phase} cycle={state.current_cycle}/{state.total_cycles} error={state.error!r}')
"

echo "Starting full runner for remaining cycles…"
nohup "${PY}" -u -m blast_lib.iterative_loop.runner >>"${ROOT}/.cursor/iterative_loop/runner.log" 2>&1 &
echo $! >"${ROOT}/.cursor/iterative_loop/runner.pid"
echo "Runner pid $(cat "${ROOT}/.cursor/iterative_loop/runner.pid")"
