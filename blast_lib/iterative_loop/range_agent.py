"""RangeAgent — best trial + changemodel.json.py + mcts_restart update."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

from blast_lib.agenticblast_submit import normalize_run_path
from blast_lib.changemodel_bounds import TERSEOFF_PARAM_COUNT
from blast_lib.config_types import UIConfig
from blast_lib.iterative_loop.ho_report_utils import best_trial_from_report, sync_and_report_path
from blast_lib.remote import RemoteError, ssh_exec, ssh_write_file

DEFAULT_SB_PREFIX = "Sb Sb Sb 1"
_FLOAT_RE = re.compile(r"-?[\d]+(?:\.[\d]*)?(?:[eE][+-]?\d+)?")


@dataclass
class RangeUpdateResult:
    ok: bool
    message: str
    best_score: float | None = None
    best_iteration: int | None = None


def extract_tersoff_param_strings(input_params: str) -> list[str]:
    """Thirteen numeric tokens from ho.report input line (after element-pair prefix)."""
    text = input_params.strip()
    if ":" in text:
        text = text.split(":", 1)[1].strip()
    tokens = _FLOAT_RE.findall(text)
    if len(tokens) < TERSEOFF_PARAM_COUNT:
        raise ValueError(
            f"Expected {TERSEOFF_PARAM_COUNT} parameters in input line, found {len(tokens)}"
        )
    return tokens[-TERSEOFF_PARAM_COUNT:]


def extract_tersoff_floats(input_params: str) -> list[float]:
    return [float(x) for x in extract_tersoff_param_strings(input_params)]


def split_mcts_restart_line(text: str) -> tuple[str, list[float]]:
    parts = text.strip().split()
    if len(parts) < TERSEOFF_PARAM_COUNT:
        raise ValueError("mcts_restart.tersoff too short")
    floats = [float(x) for x in parts[-TERSEOFF_PARAM_COUNT:]]
    prefix = " ".join(parts[:-TERSEOFF_PARAM_COUNT]).strip() or DEFAULT_SB_PREFIX
    return prefix, floats


def format_mcts_restart_line(prefix: str, values: list[float]) -> str:
    if len(values) != TERSEOFF_PARAM_COUNT:
        raise ValueError(f"Need {TERSEOFF_PARAM_COUNT} values for mcts_restart")
    nums = " ".join(f"{v:.6f}" for v in values)
    return f"{prefix} {nums}\n"


class RangeAgent:
    def __init__(self, config: UIConfig) -> None:
        self.config = config

    def run(self, run_folder: str, *, report_already_synced: bool = False) -> RangeUpdateResult:
        folder = normalize_run_path(self.config, run_folder)
        try:
            if report_already_synced:
                from blast_lib.run_catalog import find_report_path

                rp = find_report_path(self.config, folder)
                if not rp.is_file():
                    sync_and_report_path(self.config, folder)
                    rp = find_report_path(self.config, folder)
            else:
                rp = sync_and_report_path(self.config, folder)

            trial = best_trial_from_report(rp)
            input_params = trial.get("input_params") or ""
            param_strings = extract_tersoff_param_strings(input_params)
            param_floats = [float(x) for x in param_strings]

            args = " ".join(shlex.quote(s) for s in param_strings)
            remote_cmd = (
                f"cd {shlex.quote(folder)} && "
                f"{shlex.quote(self.config.blast_python)} changemodel.json.py {args}"
            )
            out = ssh_exec(self.config, remote_cmd, timeout=120)

            restart_path = f"{folder}/mcts_restart.tersoff"
            try:
                existing = ssh_exec(self.config, f"cat {shlex.quote(restart_path)}", timeout=30)
                prefix, _ = split_mcts_restart_line(existing)
            except RemoteError:
                prefix = DEFAULT_SB_PREFIX

            body = format_mcts_restart_line(prefix, param_floats)
            ssh_write_file(self.config, restart_path, body)

            msg = (out or "changemodel.json.py completed").strip()
            return RangeUpdateResult(
                ok=True,
                message=msg,
                best_score=trial.get("score"),
                best_iteration=trial.get("iteration"),
            )
        except (RemoteError, ValueError, OSError) as exc:
            return RangeUpdateResult(ok=False, message=str(exc))
