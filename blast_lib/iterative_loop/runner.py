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
from blast_lib.iterative_loop.state import Phase, load_state  # noqa: E402


def run_loop(*, once: bool = False, poll_sec: int | None = None) -> int:
    load_repo_dotenv()
    config = load_config()
    interval = poll_sec if poll_sec is not None else config.iterative_loop_poll_sec
    controller = IterativeRunController(config)

    while True:
        state = load_state(config)
        if is_workflow_active(state):
            controller.tick()
        if once:
            return 0
        time.sleep(max(5, interval))


def main() -> None:
    parser = argparse.ArgumentParser(description="BLAST autonomous iterative loop runner")
    parser.add_argument("--once", action="store_true", help="Single controller tick then exit")
    parser.add_argument("--poll-sec", type=int, default=None)
    args = parser.parse_args()
    try:
        raise SystemExit(run_loop(once=args.once, poll_sec=args.poll_sec))
    except KeyboardInterrupt:
        raise SystemExit(0) from None


if __name__ == "__main__":
    main()
