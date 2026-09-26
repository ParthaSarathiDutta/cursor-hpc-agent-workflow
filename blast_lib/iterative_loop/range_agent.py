"""RangeAgent — best trial + changemodel.json.py + mcts_restart update."""

from __future__ import annotations

import shlex
from blast_lib.agenticblast_submit import normalize_run_path
from blast_lib.config_types import UIConfig
from blast_lib.iterative_loop.ho_report_utils import best_trial_from_report, sync_and_report_path
from blast_lib.iterative_loop.tersoff_params import (  # re-exported for tests/callers
    DEFAULT_SB_PREFIX,
    extract_tersoff_floats,
    extract_tersoff_param_strings,
    format_mcts_restart_line,
    split_mcts_restart_line,
)
from blast_lib.iterative_loop.range_types import RangeUpdateResult
from blast_lib.remote import RemoteError, ssh_exec, ssh_write_file


__all__ = [
    "RangeUpdateResult",
    "RangeAgent",
    "DEFAULT_SB_PREFIX",
    "extract_tersoff_floats",
    "extract_tersoff_param_strings",
    "format_mcts_restart_line",
    "split_mcts_restart_line",
]


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
