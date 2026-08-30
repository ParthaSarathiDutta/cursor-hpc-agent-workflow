"""Load dashboard configuration from config/ui.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "ui.yaml"


@dataclass
class UIConfig:
    ssh_host: str = "perlmutter"
    blast_root: str = "/global/cfs/cdirs/m4597/partha/AgenticBLAST"
    local_cache: str = "~/blast-runs-cache"
    gpu_account: str = "YOUR_GPU_ACCOUNT_g"
    slurm_script: str = "slurm/blast_train.slurm"
    run_folders: list[str] = field(
        default_factory=lambda: [
            "ML-Tersoff-1_PE",
            "ML-Tersoff-1_PE_12",
            "ML-Tersoff-1_PE_hybrid",
        ]
    )
    trial_target: int = 1000
    status_board_path: str = ".cursor/status/board.json"
    plans_dir: str = ".cursor/plans"

    @property
    def local_cache_path(self) -> Path:
        return Path(self.local_cache).expanduser().resolve()

    @property
    def status_board(self) -> Path:
        return (REPO_ROOT / self.status_board_path).resolve()

    @property
    def plans_path(self) -> Path:
        candidate = REPO_ROOT / self.plans_dir
        if candidate.is_dir():
            return candidate
        return Path.home() / ".cursor" / "plans"


def load_config(path: Path | None = None) -> UIConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        example = REPO_ROOT / "config" / "ui.yaml.example"
        if example.is_file():
            config_path = example
        else:
            return UIConfig()

    with config_path.open() as fh:
        raw = yaml.safe_load(fh) or {}

    fields = UIConfig.__dataclass_fields__
    return UIConfig(**{k: v for k, v in raw.items() if k in fields})


def run_dir(config: UIConfig, folder: str) -> Path:
    return config.local_cache_path / folder


def report_path(config: UIConfig, folder: str) -> Path:
    return run_dir(config, folder) / "reports" / "ho.report"
