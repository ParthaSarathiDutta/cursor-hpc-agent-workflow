"""Parse BLAST ho.report trial records."""

from __future__ import annotations

import re
from pathlib import Path

FINALOBJ_RE = re.compile(r"^\#\s*([\d.]+)\s*\|\s*finalObj\s*\|")
INPUT_RE = re.compile(r"^input\s+")


def parse_ho_report(report_path: Path) -> list[dict]:
    """Return one record per ``input`` line in the report."""
    trials: list[dict] = []
    current: dict | None = None

    with report_path.open() as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n")

            if INPUT_RE.match(line):
                current = {
                    "iteration": len(trials) + 1,
                    "score": None,
                    "status": "pending",
                    "reason": "",
                }
                trials.append(current)
                continue

            if current is None:
                continue

            if "invalid parameter" in line:
                current["score"] = 1_000_000.0
                current["status"] = "invalid"
                current["reason"] = line.lstrip("# ").strip()
                current = None
                continue

            mobj = FINALOBJ_RE.match(line)
            if mobj:
                current["score"] = float(mobj.group(1))
                current["status"] = "final"
                tail = line.split("| finalObj |", 1)[-1].strip()
                if "DUMP" in tail:
                    current["reason"] = tail.split("DUMP", 1)[-1].strip()
                else:
                    current["reason"] = tail
                current = None

    return trials
