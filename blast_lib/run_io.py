"""Load run inputs/outputs from user-provided paths."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from blast_lib.config import UIConfig
from blast_lib.metrics import infer_stage, summarize_run, top_k_trials
from blast_lib.parser import parse_ho_report
from blast_lib.remote import RemoteError, ssh_exec
from blast_lib.user_session import local_cache_dir, run_folder_name

MODEL_HEADER_RE = re.compile(r"tersoff.*?parameters.*?\|\s*(\S+)", re.I)


@dataclass
class PropertyRow:
    stage: str
    detail: str
    status: str


@dataclass
class RunOutputs:
    run_folder_path: str
    run_name: str
    best_score: float | None = None
    deepest_stage: str = "none"
    completed_all: bool = False
    best_params: str | None = None
    input_params: str | None = None
    failure_reason: str | None = None
    properties: list[PropertyRow] = field(default_factory=list)
    trial_count: int = 0
    report_exists: bool = False


def read_remote_file(config: UIConfig, remote_path: str) -> str | None:
    try:
        return ssh_exec(config, f"cat '{remote_path}'", timeout=20)
    except RemoteError:
        return None


def parse_model_json(text: str | None) -> tuple[str | None, int | None, str]:
    if not text:
        return None, None, ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, None, f"Invalid JSON: {exc}"

    element_pair = None
    n_params = 0
    model_block = data.get("model") or {}
    for key, val in model_block.items():
        mobj = MODEL_HEADER_RE.search(key)
        if mobj:
            element_pair = mobj.group(1)
        if isinstance(val, dict):
            for param_key in val:
                if param_key.startswith("?"):
                    continue
                if "∈" in param_key or "[" in str(val[param_key]):
                    n_params += 1

    preview = json.dumps(data, indent=2)
    if len(preview) > 4000:
        preview = preview[:4000] + "\n... (truncated)"
    return element_pair, n_params or None, preview


def _read_local(path: Path) -> str | None:
    return path.read_text() if path.is_file() else None


def _properties_from_trial(trial: dict) -> list[PropertyRow]:
    rows: list[PropertyRow] = []
    reason = trial.get("reason") or ""
    stage = infer_stage(reason)

    if "completed all stages" in reason.lower():
        rows.append(PropertyRow("all", "Completed full property ladder", "pass"))
    elif stage != "unknown":
        rows.append(PropertyRow(stage, reason, "fail"))

    for line in trial.get("stage_lines") or []:
        rows.append(PropertyRow("stage", line.strip(), "info"))

    if not rows and reason:
        rows.append(PropertyRow("summary", reason, "info"))

    return rows


def load_run_outputs(
    config: UIConfig,
    run_folder_path: str,
    use_ssh: bool = True,
    sync_first: bool = False,
) -> RunOutputs:
    from blast_lib.remote import sync_run_at_path

    name = run_folder_name(run_folder_path)
    outputs = RunOutputs(run_folder_path=run_folder_path, run_name=name)
    local = local_cache_dir(config, run_folder_path)
    report = local / "reports" / "ho.report"

    if sync_first and use_ssh:
        try:
            sync_run_at_path(config, run_folder_path)
        except (RemoteError, OSError):
            pass

    for fname in ("mcts_restart.tersoff", "mcts_restart"):
        text = _read_local(local / fname)
        if not text and use_ssh:
            text = read_remote_file(config, f"{run_folder_path.rstrip('/')}/{fname}")
        if text:
            outputs.best_params = text.strip()
            break

    if not report.is_file():
        return outputs

    outputs.report_exists = True
    trials = parse_ho_report(report)
    outputs.trial_count = len(trials)
    summary = summarize_run(name, trials, report_exists=True)
    outputs.best_score = summary.best_score
    outputs.deepest_stage = summary.deepest_stage

    top = top_k_trials(trials, k=1)
    if top:
        best = top[0]
        outputs.failure_reason = best.get("reason")
        outputs.input_params = best.get("input_params")
        outputs.completed_all = "completed all stages" in (best.get("reason") or "").lower()
        outputs.properties = _properties_from_trial(best)

    return outputs
