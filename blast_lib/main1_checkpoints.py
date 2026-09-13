"""Parse checkpoint thresholds from run-folder main1.py."""

from __future__ import annotations

import re

from blast_lib.config import UIConfig
from blast_lib.remote import RemoteError, ssh_exec
from blast_lib.user_session import local_cache_dir

STAGE_ORDER = ["lattice", "ce", "eos", "phonon", "elastic"]

_PROP_RE = re.compile(r"""^\s*prop\s*=\s*['"](\w+)['"]""")
_CHECKPOINT_RE = re.compile(r"\.checkpoint\s*\(")
_CONDITION_RE = re.compile(r'"([^"]*(?:<=|>=|==|!=|<|>)[^"]*)"')


def _normalize_stage(name: str) -> str:
    n = name.lower()
    if n in ("cohesive_e", "cohesive", "cohesiveenergy"):
        return "ce"
    return n


def parse_main1_checkpoints(source: str) -> dict[str, list[str]]:
    """Extract active checkpoint condition strings keyed by property stage."""
    stages: dict[str, list[str]] = {}
    current_prop: str | None = None
    lines = source.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]
        prop_m = _PROP_RE.match(line)
        if prop_m:
            current_prop = _normalize_stage(prop_m.group(1))

        if _CHECKPOINT_RE.search(line):
            block_lines = [line]
            j = i
            while "]" not in block_lines[-1] and j + 1 < len(lines):
                j += 1
                block_lines.append(lines[j])

            stage = current_prop
            block_text = "\n".join(block_lines)
            if re.search(r"\.checkpoint\s*\(\s*['\"]phonon['\"]", block_text):
                stage = "phonon"
            elif re.search(r"\.checkpoint\s*\(\s*prop", block_text) and current_prop:
                stage = current_prop

            if not stage:
                i = j + 1
                continue

            conditions: list[str] = []
            for bl in block_lines:
                stripped = bl.strip()
                if stripped.startswith("#"):
                    continue
                code = bl.split("#", 1)[0]
                for m in _CONDITION_RE.finditer(code):
                    cond = m.group(1).strip()
                    if cond and cond not in conditions:
                        conditions.append(cond)

            if conditions:
                bucket = stages.setdefault(stage, [])
                for c in conditions:
                    if c not in bucket:
                        bucket.append(c)

            i = j + 1
            continue

        i += 1

    return {s: stages[s] for s in STAGE_ORDER if s in stages}


def _resolve_run_path(config: UIConfig, run_path: str) -> str:
    text = run_path.strip()
    if text.startswith("/"):
        return text.rstrip("/")
    return f"{config.blast_root.rstrip('/')}/{text}"


def load_main1_text(config: UIConfig, run_path: str) -> str | None:
    remote = _resolve_run_path(config, run_path)
    cached = local_cache_dir(config, remote) / "main1.py"
    if cached.is_file():
        return cached.read_text()
    try:
        text = ssh_exec(config, f"cat '{remote}/main1.py'", timeout=20)
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(text)
        return text
    except RemoteError:
        return None


def load_main1_checkpoints(config: UIConfig, run_path: str) -> dict[str, list[str]]:
    text = load_main1_text(config, run_path)
    if not text:
        return {}
    return parse_main1_checkpoints(text)


def format_checkpoint_config(checkpoint_config: dict[str, list[str]]) -> str:
    if not checkpoint_config:
        return "Configured checkpoints (main1.py): not available — Sync folder or check SSH."
    lines = ["Configured checkpoints (from main1.py):"]
    for stage in STAGE_ORDER:
        rules = checkpoint_config.get(stage)
        if rules:
            lines.append(f"  - {stage}: {'; '.join(rules)}")
    return "\n".join(lines)
