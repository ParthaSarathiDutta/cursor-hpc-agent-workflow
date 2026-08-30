"""Rule-based next-run suggestions from ho.report metrics."""

from __future__ import annotations

from dataclasses import dataclass

from blast_lib.metrics import RunSummary, infer_stage, scored_trials, stage_breakdown, top_k_trials


@dataclass
class Suggestion:
    priority: str
    title: str
    detail: str


def suggest_for_run(folder: str, trials: list[dict], summary: RunSummary) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    if not summary.report_exists:
        suggestions.append(Suggestion("high", "Sync run data", f"No ho.report for {folder}. Sync from Perlmutter first."))
        return suggestions

    breakdown = stage_breakdown(trials)
    total_scored = summary.scored_count or 1
    lattice_frac = breakdown.get("lattice", 0) / total_scored

    top = top_k_trials(trials, k=1)
    best_stage = top[0]["stage"] if top else "unknown"

    if lattice_frac > 0.8:
        suggestions.append(Suggestion(
            "high",
            "Avoid dual-polymorph everywhere",
            f"{folder}: {lattice_frac:.0%} of trials fail at lattice. Prefer hybrid CE-only dual polymorph (see strategy.md).",
        ))

    if best_stage == "ce":
        suggestions.append(Suggestion(
            "high",
            "Try hybrid polymorph strategy",
            "Best trial stops at cohesive energy. Run ML-Tersoff-1_PE_hybrid: single polymorph for lattice/EOS/phonon/elastic, dual for CE ordering.",
        ))

    if best_stage == "elastic":
        suggestions.append(Suggestion(
            "medium",
            "Narrow bounds from top-k",
            "Best trial reached elastic. Use startmodel.py on top 3 trials to tighten model.json bounds around winners.",
        ))

    if summary.best_score and summary.best_score > 999_000:
        suggestions.append(Suggestion(
            "medium",
            "Still in penalty range",
            f"Best score {summary.best_score:,.0f} is near penalty (~1e6). Focus on top-k seeds, not bulk failed trials.",
        ))

    if not suggestions:
        suggestions.append(Suggestion(
            "low",
            "Continue monitoring",
            "Review top-k trials and compare against other run folders before next MCTS batch.",
        ))

    return suggestions
