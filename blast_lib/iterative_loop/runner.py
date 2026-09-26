"""Headless background runner for the iterative loop (same controller as the UI)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blast_lib.config import load_config  # noqa: E402
from blast_lib.env import load_repo_dotenv  # noqa: E402
from blast_lib.iterative_loop.controller import IterativeRunController, is_workflow_active  # noqa: E402
from blast_lib.iterative_loop.state import IterativeLoopState, Phase, load_state, save_state  # noqa: E402


def _run_interactive_if_ready(controller: IterativeRunController, state: IterativeLoopState) -> None:
    if state.phase != Phase.RUNNING_INTERACTIVE:
        return
    if state.interactive_launch_started:
        controller.fail_stale_interactive_launch(state)
        return
    if state.stop_requested:
        state.touch(phase=Phase.STOPPED, status_message="Stopped before interactive launch.")
        save_state(controller.config, state)
        return

    state.touch(
        interactive_launch_started=True,
        status_message=f"Interactive salloc running (cycle {state.current_cycle}/{state.total_cycles})…",
    )
    save_state(controller.config, state)

    try:
        result = controller.submit_agent.run_interactive(state.run_folder, state.walltime)
    except Exception as exc:  # noqa: BLE001
        print(f"Interactive launch error: {exc}", flush=True)
        st = load_state(controller.config)
        st.touch(
            phase=Phase.FAILED,
            interactive_launch_started=False,
            error=f"Interactive launch failed: {exc}",
            status_message=f"Interactive launch failed: {exc}",
        )
        save_state(controller.config, st)
        return

    if result.allocation_job_id:
        mid = load_state(controller.config)
        mid.touch(active_job_id=result.allocation_job_id, slurm_state="ALLOCATED")
        save_state(controller.config, mid)

    controller.finish_interactive_cycle(result)


def run_loop(*, once: bool = False, poll_sec: int | None = None) -> int:
    print("Iterative loop runner started", flush=True)
    load_repo_dotenv()
    config = load_config()
    interval = poll_sec if poll_sec is not None else config.iterative_loop_poll_sec
    controller = IterativeRunController(config)

    while True:
        state = load_state(config)
        if state.phase == Phase.RUNNING_INTERACTIVE:
            _run_interactive_if_ready(controller, state)
        elif is_workflow_active(state):
            controller.tick()
        if once:
            return 0
        time.sleep(max(5, interval))


def main() -> None:
    parser = argparse.ArgumentParser(description="BLAST autonomous iterative loop runner")
    parser.add_argument("--once", action="store_true", help="Single iteration then exit")
    parser.add_argument("--poll-sec", type=int, default=None)
    args = parser.parse_args()
    try:
        raise SystemExit(run_loop(once=args.once, poll_sec=args.poll_sec))
    except KeyboardInterrupt:
        raise SystemExit(0) from None


if __name__ == "__main__":
    main()
