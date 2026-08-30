"""Optional LLM strategy layer (requires GOOGLE_API_KEY)."""

from __future__ import annotations

import os


def llm_available() -> bool:
    return bool(os.environ.get("GOOGLE_API_KEY"))


def generate_llm_strategy(prompt: str) -> str:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return "Set GOOGLE_API_KEY to enable LLM strategy suggestions."

    try:
        import google.generativeai as genai
    except ImportError:
        return "Install google-generativeai: pip install google-generativeai"

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    response = model.generate_content(prompt)
    return response.text or "(No response)"
