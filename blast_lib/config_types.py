"""UIConfig dataclass — isolated from load logic to survive Streamlit hot reload."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


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
    dashboard_url: str = "http://127.0.0.1:8501"
    notify_email: str = ""
    google_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    chat_context_top_k: int = 5
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
