"""Read agent status board and plan todos for the Activity page."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from blast_lib.config import REPO_ROOT, UIConfig, load_config


@dataclass
class PlanTodo:
    id: str
    content: str
    status: str


@dataclass
class AgentSnapshot:
    status: str
    current_task: str
    last_action: str
    started_at: datetime | None
    finished_at: datetime | None
    elapsed_seconds: float
    eta_seconds: float | None
    eta_label: str
    subagent: str | None
    active_plan: str | None
    plan_name: str | None
    todos: list[PlanTodo]
    session_id: str | None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _find_active_plan(config: UIConfig, board: dict) -> Path | None:
    if board.get("active_plan"):
        p = Path(board["active_plan"])
        if not p.is_absolute():
            p = REPO_ROOT / p
        if p.is_file():
            return p
        alt = Path.home() / ".cursor" / "plans" / Path(board["active_plan"]).name
        if alt.is_file():
            return alt

    plans_dir = config.plans_path
    if not plans_dir.is_dir():
        return None
    candidates = sorted(plans_dir.glob("*.plan.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def parse_plan_todos(plan_path: Path) -> tuple[str | None, list[PlanTodo]]:
    text = plan_path.read_text()
    if not text.startswith("---"):
        return None, []
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, []
    frontmatter = yaml.safe_load(parts[1]) or {}
    name = frontmatter.get("name")
    todos_raw = frontmatter.get("todos") or []
    todos = [
        PlanTodo(
            id=str(t.get("id", i)),
            content=str(t.get("content", "")),
            status=str(t.get("status", "pending")),
        )
        for i, t in enumerate(todos_raw)
    ]
    return name, todos


def _compute_eta(elapsed: float, todos: list[PlanTodo]) -> tuple[float | None, str]:
    if not todos:
        return None, "No plan steps defined"
    completed = sum(1 for t in todos if t.status == "completed")
    in_progress = sum(1 for t in todos if t.status == "in_progress")
    total = len(todos)
    done_weight = completed + (0.5 * in_progress)
    if done_weight <= 0:
        return None, f"Plan started — {total} steps total"
    remaining = max(total - done_weight, 0.5)
    rate = elapsed / done_weight
    eta = rate * remaining
    return eta, f"~{ _format_duration(eta) } remaining ({completed}/{total} done)"


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def load_agent_snapshot(config: UIConfig | None = None) -> AgentSnapshot:
    config = config or load_config()
    board_path = config.status_board
    board: dict = {}
    if board_path.is_file():
        try:
            board = json.loads(board_path.read_text())
        except json.JSONDecodeError:
            board = {}

    started = _parse_iso(board.get("started_at"))
    finished = _parse_iso(board.get("finished_at"))
    now = datetime.now(timezone.utc)
    if started and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if finished and finished.tzinfo is None:
        finished = finished.replace(tzinfo=timezone.utc)

    if started:
        end = finished or now
        elapsed = (end - started).total_seconds()
    else:
        elapsed = 0.0

    plan_path = _find_active_plan(config, board)
    plan_name = None
    todos: list[PlanTodo] = []
    active_plan_str = None
    if plan_path:
        active_plan_str = str(plan_path)
        plan_name, todos = parse_plan_todos(plan_path)

    status = board.get("status", "idle")
    eta_seconds, eta_label = _compute_eta(elapsed, todos) if status == "active" else (None, "Idle — waiting for next task")

    return AgentSnapshot(
        status=status,
        current_task=board.get("current_task") or "No active task",
        last_action=board.get("last_action") or "—",
        started_at=started,
        finished_at=finished,
        elapsed_seconds=elapsed,
        eta_seconds=eta_seconds,
        eta_label=eta_label,
        subagent=board.get("subagent"),
        active_plan=active_plan_str,
        plan_name=plan_name,
        todos=todos,
        session_id=board.get("session_id"),
    )
