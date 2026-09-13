"""Agentic chat — Gemini with function calling over blast_lib tools."""

from __future__ import annotations

from dataclasses import dataclass, field

from blast_lib.agent_tools import build_toolkit
from blast_lib.config import UIConfig
from blast_lib.gemini_client import gemini_api_key, gemini_model, gemini_model_candidates, llm_available
from blast_lib.run_catalog import load_catalog
from blast_lib.user_session import UserRunSession


@dataclass
class ChatMessage:
    role: str  # user | assistant
    content: str


@dataclass
class ChatReply:
    text: str
    tools_used: list[str] = field(default_factory=list)
    model: str = ""


@dataclass
class ChatState:
    messages: list[ChatMessage] = field(default_factory=list)


def _history_for_gemini(history: list[ChatMessage]) -> list[dict]:
    out: list[dict] = []
    for msg in history:
        role = "user" if msg.role == "user" else "model"
        out.append({"role": role, "parts": [msg.content]})
    return out


def _tools_used_since(history_len: int, chat) -> list[str]:
    names: list[str] = []
    try:
        entries = chat.history[int(history_len) :]
    except (TypeError, IndexError):
        entries = chat.history
    for entry in entries:
        for part in entry.parts:
            fc = getattr(part, "function_call", None)
            if fc and fc.name and fc.name not in names:
                names.append(fc.name)
    return names


def chat_reply(
    config: UIConfig,
    session: UserRunSession | None,
    history: list[ChatMessage],
    user_message: str,
) -> ChatReply:
    api_key = gemini_api_key(config)
    if not api_key:
        return ChatReply(
            text=(
                "Chat needs a Google API key. Set GOOGLE_API_KEY or GEMINI_API_KEY in .env, "
                "or add google_api_key to config/ui.yaml."
            )
        )

    try:
        import google.generativeai as genai
    except ImportError:
        return ChatReply(text="Install google-generativeai: pip install google-generativeai")

    toolkit = build_toolkit(config, session)
    genai.configure(api_key=api_key)

    errors: list[str] = []
    for model_name in gemini_model_candidates(config):
        try:
            model = genai.GenerativeModel(
                model_name,
                system_instruction=toolkit.system_instruction(),
                tools=toolkit.tool_functions(),
            )
            chat = model.start_chat(
                history=_history_for_gemini(history),
                enable_automatic_function_calling=True,
            )
            hist_before = len(chat.history)
            response = chat.send_message(user_message)
            text = (response.text or "(No response)").strip()
            tools = _tools_used_since(hist_before, chat)
            if tools:
                text = f"*Tools used: {', '.join(tools)}*\n\n{text}"
            return ChatReply(text=text, tools_used=tools, model=model_name)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{model_name}: {exc}")

    return ChatReply(
        text=(
            "All Gemini models failed. Tried: "
            + ", ".join(gemini_model_candidates(config))
            + ".\n\n"
            + "\n".join(errors[:3])
        )
    )


def build_context_summary(config: UIConfig, session: UserRunSession | None) -> str:
    """Short index for UI — agent fetches details via tools."""
    lines = ["Agentic mode: assistant calls tools to read ho.report on demand.", ""]
    for e in load_catalog(config, session, load_main1=False):
        if e.report_exists:
            lines.append(f"- {e.name}: best_stage={e.best_stage}, trials={e.trial_count}")
        else:
            lines.append(f"- {e.name}: (sync ho.report first)")
    lines.append("")
    lines.append(f"Model: {gemini_model(config)}")
    return "\n".join(lines)
