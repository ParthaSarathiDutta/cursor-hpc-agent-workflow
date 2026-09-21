"""Pending next-job instructions from the user (human-in-the-loop)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from blast_lib.config import REPO_ROOT, UIConfig


@dataclass
class JobInstruction:
    run_folder_path: str
    instructions: str
    bound_tighten_pct: float = 10.0
    use_mcts: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "pending"  # pending | submitted | failed


INSTRUCTIONS_PATH = REPO_ROOT / ".cursor" / "status" / "job_instructions.json"


def save_instruction(record: JobInstruction) -> None:
    INSTRUCTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    INSTRUCTIONS_PATH.write_text(json.dumps(asdict(record), indent=2))


def load_instruction() -> JobInstruction | None:
    if not INSTRUCTIONS_PATH.is_file():
        return None
    raw = json.loads(INSTRUCTIONS_PATH.read_text())
    return JobInstruction(**raw)


def plan_summary(record: JobInstruction) -> str:
    lines = [
        f"Run folder: {record.run_folder_path}",
        f"User instructions: {record.instructions}",
        "",
        "Agent interpretation (human must confirm before submit):",
        f"- Seed: mcts_restart.tersoff from best set in this folder",
        f"- Bounds: changemodel.json.py ±{record.bound_tighten_pct:.0f}% around best trial (if tightening requested)",
        f"- Search: {'MCTS (RunBOP.py)' if record.use_mcts else 'one-shot only (not recommended for next search)'}",
        "",
        "Manual steps on Perlmutter:",
        "1. Apply main1.py / model.json / checkpoint changes on login node if needed",
        "2. Run changemodel.json.py or startmodel.py if tightening bounds",
        "3. Dashboard **Submit Next Job** → write input.txt → salloc → parallel RunBOP.py",
    ]
    return "\n".join(lines)
