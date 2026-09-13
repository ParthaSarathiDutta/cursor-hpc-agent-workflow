"""Shared Gemini model + API key helpers."""

from __future__ import annotations

import os

from blast_lib.config import UIConfig
from blast_lib.env import load_repo_dotenv

# Google retires older models for new keys — keep fallbacks in sync with API errors.
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
FALLBACK_GEMINI_MODELS = (
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.0-flash",
)


def gemini_api_key(config: UIConfig | None = None) -> str | None:
    load_repo_dotenv()
    for source in (
        os.environ.get("GOOGLE_API_KEY"),
        os.environ.get("GEMINI_API_KEY"),
        getattr(config, "google_api_key", "") if config else "",
    ):
        if source:
            return source
    return None


def gemini_model(config: UIConfig | None = None) -> str:
    return (
        os.environ.get("GEMINI_MODEL")
        or (getattr(config, "gemini_model", "") if config else "")
        or DEFAULT_GEMINI_MODEL
    )


def gemini_model_candidates(config: UIConfig | None = None) -> list[str]:
    """Preferred model first, then fallbacks (deduplicated)."""
    preferred = gemini_model(config)
    seen: set[str] = set()
    out: list[str] = []
    for name in (preferred, *FALLBACK_GEMINI_MODELS):
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def llm_available(config: UIConfig | None = None) -> bool:
    return bool(gemini_api_key(config))
