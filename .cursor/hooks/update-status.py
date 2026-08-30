#!/usr/bin/env python3
"""Write agent activity to .cursor/status/board.json for the BLAST dashboard."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BOARD_PATH = REPO_ROOT / ".cursor" / "status" / "board.json"
PLANS_HOME = Path.home() / ".cursor" / "plans"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_board() -> dict:
    if BOARD_PATH.is_file():
        try:
            return json.loads(BOARD_PATH.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def save_board(board: dict) -> None:
    BOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    BOARD_PATH.write_text(json.dumps(board, indent=2))


def latest_plan() -> str | None:
    if not PLANS_HOME.is_dir():
        return None
    plans = sorted(PLANS_HOME.glob("*.plan.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(plans[0]) if plans else None


def summarize_tool(data: dict) -> str:
    tool = data.get("tool_name") or data.get("tool") or "tool"
    tool_input = data.get("tool_input") or data.get("input") or {}
    if isinstance(tool_input, str):
        return f"{tool}: {tool_input[:120]}"
    if tool in ("Read", "Write", "StrReplace"):
        path = tool_input.get("path") or tool_input.get("target_notebook") or ""
        return f"{tool} {Path(str(path)).name}" if path else tool
    if tool == "Shell":
        cmd = tool_input.get("command") or tool_input.get("description") or ""
        return f"Shell: {str(cmd)[:100]}"
    if tool == "Task":
        desc = tool_input.get("description") or tool_input.get("prompt") or ""
        return f"Task: {str(desc)[:100]}"
    return str(tool)


def main() -> None:
    event = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    board = load_board()

    if event == "sessionStart":
        board = {
            "session_id": data.get("conversation_id") or str(uuid.uuid4()),
            "status": "active",
            "started_at": now_iso(),
            "finished_at": None,
            "current_task": "Agent session started",
            "last_action": "sessionStart",
            "subagent": None,
            "active_plan": latest_plan(),
        }
    elif event == "postToolUse":
        board.setdefault("status", "active")
        board["last_action"] = summarize_tool(data)
        board["current_task"] = board["last_action"]
        if not board.get("active_plan"):
            board["active_plan"] = latest_plan()
    elif event == "afterShellExecution":
        cmd = data.get("command") or data.get("full_command") or "shell"
        board.setdefault("status", "active")
        board["last_action"] = f"Shell: {str(cmd)[:120]}"
        board["current_task"] = board["last_action"]
    elif event == "subagentStart":
        board.setdefault("status", "active")
        board["subagent"] = data.get("subagent_type") or data.get("type") or "subagent"
        board["current_task"] = f"Subagent: {board['subagent']}"
    elif event == "subagentStop":
        board["subagent"] = None
        board["last_action"] = "Subagent finished"
    elif event in ("stop", "sessionEnd"):
        board["status"] = "complete"
        board["finished_at"] = now_iso()
        board["current_task"] = "Session complete"
    else:
        board["last_action"] = event

    save_board(board)


if __name__ == "__main__":
    main()
