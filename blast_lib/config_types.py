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
    # AgenticBLAST submit (input.txt + interactive salloc + parallel RunBOP.py)
    input_txt_name: str = "input.txt"
    run_dir_glob: str = "ML-Tersoff*"
    blast_python: str = "/global/cfs/cdirs/m1917/blast_ff/bin/miniconda3/bin/python"
    submit_account: str = "m3794"
    salloc_nodes: int = 2
    salloc_time: str = "00:10:00"
    salloc_ntasks_per_node: int = 4
    salloc_gpus_per_task: int = 1
    salloc_gpus: int = 8
    salloc_qos: str = "interactive"
    batch_slurm_script: str = "slurm/agenticblast_runBOP.slurm"
    batch_slurm_remote_name: str = "agenticblast_runBOP.slurm"
    batch_qos: str = "regular"
    batch_time: str = "04:00:00"
    batch_nodes: int = 2
    batch_ntasks_per_node: int = 4
    batch_gpus_per_task: int = 1
    batch_gpus: int = 8
    launch_ssh_timeout_sec: int = 14_400
    iterative_loop_state_path: str = ".cursor/status/iterative_loop.json"
    iterative_loop_poll_sec: int = 30

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

    @property
    def input_txt_remote_path(self) -> str:
        return f"{self.blast_root.rstrip('/')}/{self.input_txt_name}"

    @property
    def batch_slurm_remote_path(self) -> str:
        return f"{self.blast_root.rstrip('/')}/{self.batch_slurm_remote_name}"

    @property
    def iterative_loop_state_file(self) -> Path:
        return (REPO_ROOT / self.iterative_loop_state_path).resolve()
