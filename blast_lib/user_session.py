"""User-provided run paths — no assumed folders."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class UserRunSession:
    connected: bool = False
    training_data_path: str = ""
    model_json_path: str = ""
    model_type: str = "Tersoff"
    optimizer: str = "Monte Carlo Tree Search (MCTS)"
    run_folder_path: str = ""
    model_loaded: bool = False
    model_preview: str = ""
    element_pair: str | None = None
    n_search_params: int | None = None
    saved_runs: list[str] = field(default_factory=list)


SESSION_KEY = "user_run"


def get_session() -> UserRunSession:
    import streamlit as st

    if SESSION_KEY not in st.session_state:
        st.session_state[SESSION_KEY] = UserRunSession()
    raw = st.session_state[SESSION_KEY]
    if isinstance(raw, UserRunSession):
        return raw
    return UserRunSession(**raw) if isinstance(raw, dict) else UserRunSession()


def save_session(session: UserRunSession) -> None:
    import streamlit as st

    st.session_state[SESSION_KEY] = session


def run_folder_name(run_folder_path: str) -> str:
    return Path(run_folder_path.rstrip("/")).name or run_folder_path


def local_cache_dir(config, run_folder_path: str) -> Path:
    key = run_folder_path.rstrip("/").replace("/", "__")
    return config.local_cache_path / "runs" / key


def cached_report_path(config, run_folder_path: str) -> Path:
    return local_cache_dir(config, run_folder_path) / "reports" / "ho.report"


def connected_run_paths(session: UserRunSession) -> list[str]:
    paths = list(session.saved_runs)
    if session.run_folder_path and session.run_folder_path not in paths:
        paths.append(session.run_folder_path)
    return [p for p in paths if p.strip()]
