"""Optional LLM strategy layer (requires GOOGLE_API_KEY)."""

from __future__ import annotations

from blast_lib.config import load_config
from blast_lib.gemini_client import gemini_api_key, gemini_model, llm_available

__all__ = ["generate_llm_strategy", "llm_available"]


def generate_llm_strategy(prompt: str) -> str:
    config = load_config()
    api_key = gemini_api_key(config)
    if not api_key:
        return "Set GOOGLE_API_KEY or GEMINI_API_KEY to enable LLM strategy suggestions."

    try:
        import google.generativeai as genai
    except ImportError:
        return "Install google-generativeai: pip install google-generativeai"

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(gemini_model(config))
    response = model.generate_content(prompt)
    return response.text or "(No response)"
