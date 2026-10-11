"""Load dashboard configuration from config/ui.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

from blast_lib.config_types import REPO_ROOT, UIConfig  # noqa: F401 — re-exported
from blast_lib.env import load_repo_dotenv

DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "ui.yaml"

__all__ = ["REPO_ROOT", "UIConfig", "DEFAULT_CONFIG_PATH", "load_config", "run_dir", "report_path"]


def load_config(path: Path | None = None) -> UIConfig:
    load_repo_dotenv()
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
