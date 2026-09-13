"""Unified run folder catalog for the dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from blast_lib.config import UIConfig, report_path
from blast_lib.metrics import infer_stage, top_k_trials
from blast_lib.parser import parse_ho_report
from blast_lib.main1_checkpoints import format_checkpoint_config, load_main1_checkpoints
from blast_lib.trial_details import METRIC_GLOSSARY, analyze_best_trial, format_analysis_text, format_trial_compact
from blast_lib.user_session import UserRunSession, connected_run_paths, local_cache_dir, run_folder_name


FOLDER_STRATEGIES: dict[str, str] = {
    "ML-Tersoff-1_PE": "Single polymorph [0] for all stages.",
    "ML-Tersoff-1_PE_12": "Dual polymorph [0, 1] for all stages.",
    "ML-Tersoff-1_PE_hybrid": "Single [0] for lattice/eos/phonon/elastic; dual [0,1] for ce only.",
}

PROPERTY_LADDER = "lattice → ce → eos → phonon → elastic"


@dataclass
class BestSetInfo:
    iteration: int | None = None
    stage: str = "none"
    failure_reason: str | None = None
    input_params: str | None = None
    restart_params: str | None = None


@dataclass
class RunCatalogEntry:
    name: str
    path: str
    strategy: str
    report_exists: bool
    trial_count: int
    best_stage: str
    best_score: float | None
    best: BestSetInfo
    completed_all: bool
    checkpoint_config: dict[str, list[str]] | None = None


def resolve_run_path(config: UIConfig, folder_or_path: str) -> str:
    text = folder_or_path.strip()
    if text.startswith("/"):
        return text.rstrip("/")
    return f"{config.blast_root.rstrip('/')}/{text}"


def find_report_path(config: UIConfig, run_path: str) -> Path:
    cached = local_cache_dir(config, run_path) / "reports" / "ho.report"
    if cached.is_file():
        return cached
    legacy = report_path(config, run_folder_name(run_path))
    if legacy.is_file():
        return legacy
    return cached


def find_restart_path(config: UIConfig, run_path: str) -> Path | None:
    for base in (local_cache_dir(config, run_path), report_path(config, run_folder_name(run_path)).parent.parent):
        for fname in ("mcts_restart.tersoff", "mcts_restart"):
            candidate = base / fname
            if candidate.is_file():
                return candidate
    return None


def strategy_for_folder(name: str) -> str:
    if name in FOLDER_STRATEGIES:
        return FOLDER_STRATEGIES[name]
    lower = name.lower()
    if "hybrid" in lower:
        return FOLDER_STRATEGIES["ML-Tersoff-1_PE_hybrid"]
    if "_12" in lower or "pe_12" in lower:
        return FOLDER_STRATEGIES["ML-Tersoff-1_PE_12"]
    if "pe" in lower:
        return FOLDER_STRATEGIES["ML-Tersoff-1_PE"]
    return "Custom run folder — check main1.py for polymorph strategy."


def list_catalog_paths(config: UIConfig, session: UserRunSession | None = None) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for folder in config.run_folders:
        path = resolve_run_path(config, folder)
        if path not in seen:
            paths.append(path)
            seen.add(path)
    if session:
        for path in connected_run_paths(session):
            if path not in seen:
                paths.append(path)
                seen.add(path)
    return paths


def load_catalog_entry(config: UIConfig, run_path: str, *, load_main1: bool = True) -> RunCatalogEntry:
    name = run_folder_name(run_path)
    rp = find_report_path(config, run_path)
    restart = find_restart_path(config, run_path)
    restart_text = restart.read_text().strip() if restart else None

    best = BestSetInfo(restart_params=restart_text)
    report_exists = rp.is_file()
    trials: list[dict] = parse_ho_report(rp) if report_exists else []
    top = top_k_trials(trials, k=1)

    if top:
        t = top[0]
        best.iteration = t.get("iteration")
        best.stage = t.get("stage") or infer_stage(t.get("reason", ""))
        best.failure_reason = t.get("reason")
        best.input_params = t.get("input_params")

    best_score = top[0]["score"] if top else None
    completed = "completed all stages" in ((best.failure_reason or "").lower())

    return RunCatalogEntry(
        name=name,
        path=run_path,
        strategy=strategy_for_folder(name),
        report_exists=report_exists,
        trial_count=len(trials),
        best_stage=best.stage,
        best_score=best_score,
        best=best,
        completed_all=completed,
        checkpoint_config=load_main1_checkpoints(config, run_path) if load_main1 else {},
    )


def load_catalog(config: UIConfig, session: UserRunSession | None = None, *, load_main1: bool = True) -> list[RunCatalogEntry]:
    return [load_catalog_entry(config, p, load_main1=load_main1) for p in list_catalog_paths(config, session)]


def catalog_context_text(entries: list[RunCatalogEntry], config: UIConfig | None = None) -> str:
    from blast_lib.config import load_config

    cfg = config or load_config()
    top_k = max(1, getattr(cfg, "chat_context_top_k", 5))
    lines = [
        f"BLAST run folders — top {top_k} scored trials per folder (from ho.report):",
        "Answer the user's question using the metrics and checkpoints below — do not dump everything unless asked.",
        "",
        METRIC_GLOSSARY.strip(),
        "",
    ]

    for e in entries:
        if not e.report_exists:
            lines.append(f"## {e.name}")
            lines.append(f"Path: {e.path}")
            lines.append("Status: no ho.report synced yet")
            lines.append("")
            continue

        rp = find_report_path(cfg, e.path)
        trials = parse_ho_report(rp)
        top = top_k_trials(trials, k=top_k)
        if not top:
            lines.append(f"## {e.name}")
            lines.append("No scored trials in ho.report.")
            lines.append("")
            continue

        analysis = analyze_best_trial(top[0], e.name)
        lines.append(format_analysis_text(e.name, top[0], analysis, e.checkpoint_config or {}))

        if len(top) > 1:
            lines.extend(["", f"Other top trials (ranks 2–{len(top)}):"])
            for rank, trial in enumerate(top[1:], start=2):
                lines.append(format_trial_compact(e.name, trial, rank, e.checkpoint_config or {}))
                lines.append("")

        lines.append("")
    return "\n".join(lines)
