"""SubmitAgent — interactive salloc + RunBOP for one run folder."""

from __future__ import annotations

from dataclasses import dataclass

from blast_lib.agenticblast_submit import (
    normalize_run_path,
    parse_salloc_job_id,
    run_interactive_cycle,
)
from blast_lib.config_types import UIConfig


@dataclass
class InteractiveSubmitResult:
    returncode: int
    log: str
    allocation_job_id: str | None = None


class SubmitAgent:
    def __init__(self, config: UIConfig) -> None:
        self.config = config

    def prepare_input(self, run_folder: str) -> None:
        folder = normalize_run_path(self.config, run_folder)
        from blast_lib.agenticblast_submit import write_input_txt

        write_input_txt(self.config, [folder])

    def run_interactive(self, run_folder: str, walltime: str) -> InteractiveSubmitResult:
        folder = normalize_run_path(self.config, run_folder)
        result = run_interactive_cycle(
            self.config,
            folder_paths=[folder],
            salloc_time=walltime,
            nodes=self.config.salloc_nodes,
            qos=self.config.salloc_qos,
            ntasks_per_node=self.config.salloc_ntasks_per_node,
            gpus_per_task=self.config.salloc_gpus_per_task,
            gpus=self.config.salloc_gpus,
            account=self.config.submit_account,
        )
        return InteractiveSubmitResult(
            returncode=result.returncode,
            log=result.log,
            allocation_job_id=parse_salloc_job_id(result.log),
        )
