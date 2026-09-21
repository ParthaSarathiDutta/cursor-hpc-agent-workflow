"""SubmitAgent — batch sbatch for one run folder."""

from __future__ import annotations

from blast_lib.agenticblast_submit import normalize_run_path, run_batch_submit
from blast_lib.config_types import UIConfig


class SubmitAgent:
    def __init__(self, config: UIConfig) -> None:
        self.config = config

    def submit(self, run_folder: str, walltime: str) -> str:
        folder = normalize_run_path(self.config, run_folder)
        result = run_batch_submit(
            self.config,
            deploy_script=True,
            batch_time=walltime,
            folder_paths=[folder],
        )
        return result.job_id
