"""Trial metrics derived from ho.report records."""

from __future__ import annotations

import re
from dataclasses import dataclass

PENALTY_THRESHOLD = 999_000.0
STAGE_PATTERNS = [
    ("elastic", re.compile(r"\belastic\b", re.I)),
    ("phonon", re.compile(r"\bphonon\b", re.I)),
    ("eos", re.compile(r"\beos\b", re.I)),
    ("ce", re.compile(r"\bce\b|cohesive", re.I)),
    ("lattice", re.compile(r"\blattice\b", re.I)),
]


def infer_stage(reason: str) -> str:
    if not reason:
        return "unknown"
    if "completed all stages" in reason.lower():
        return "complete"
    for name, pattern in STAGE_PATTERNS:
        if pattern.search(reason):
            return name
    return "unknown"


def scored_trials(trials: list[dict]) -> list[dict]:
    return [t for t in trials if t.get("score") is not None]


def best_so_far(trials: list[dict]) -> list[dict]:
    best = float("inf")
    curve: list[dict] = []
    for trial in trials:
        score = trial.get("score")
        if score is None:
            continue
        best = min(best, score)
        curve.append({"iteration": trial["iteration"], "score": score, "best": best})
    return curve


def top_k_trials(trials: list[dict], k: int = 5) -> list[dict]:
    scored = scored_trials(trials)
    ranked = sorted(scored, key=lambda t: t["score"])[:k]
    return [{**t, "stage": infer_stage(t.get("reason", ""))} for t in ranked]


@dataclass
class RunSummary:
    name: str
    trial_count: int
    scored_count: int
    best_score: float | None
    deepest_stage: str
    below_penalty_count: int
    report_exists: bool


def summarize_run(name: str, trials: list[dict], report_exists: bool = True) -> RunSummary:
    scored = scored_trials(trials)
    scores = [t["score"] for t in scored]
    best = min(scores) if scores else None

    stages_rank = {
        "complete": 6, "elastic": 5, "phonon": 4, "eos": 3, "ce": 2, "lattice": 1, "unknown": 0,
    }
    deepest = "none"
    deepest_rank = -1
    for trial in scored:
        stage = infer_stage(trial.get("reason", ""))
        rank = stages_rank.get(stage, 0)
        if rank > deepest_rank:
            deepest_rank = rank
            deepest = stage

    below_penalty = sum(1 for s in scores if s < PENALTY_THRESHOLD)
    return RunSummary(
        name=name,
        trial_count=len(trials),
        scored_count=len(scored),
        best_score=best,
        deepest_stage=deepest,
        below_penalty_count=below_penalty,
        report_exists=report_exists,
    )


def stage_breakdown(trials: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for trial in scored_trials(trials):
        stage = infer_stage(trial.get("reason", ""))
        counts[stage] = counts.get(stage, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))
