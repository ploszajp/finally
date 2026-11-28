"""LLM failure codes and the friendly texts shown to the user (planning/API_CHAT.md)."""

from __future__ import annotations

LLM_NOT_CONFIGURED = "llm_not_configured"
LLM_TIMEOUT = "llm_timeout"
LLM_UNAVAILABLE = "llm_unavailable"
LLM_INVALID_RESPONSE = "llm_invalid_response"

ERROR_MESSAGES: dict[str, str] = {
    LLM_NOT_CONFIGURED: (
        "The AI assistant is not configured. Set OPENROUTER_API_KEY in .env and restart the app. "
        "Trading and the watchlist still work."
    ),
    LLM_TIMEOUT: "The AI assistant took too long to respond. Please try again.",
    LLM_UNAVAILABLE: "The AI assistant is unavailable right now. Please try again in a moment.",
    LLM_INVALID_RESPONSE: (
        "The AI assistant returned a response I could not understand. Please try rephrasing."
    ),
}


class LLMError(Exception):
    """The LLM could not produce a usable reply. `code` is one of the constants above."""

    def __init__(self, code: str) -> None:
        if code not in ERROR_MESSAGES:
            raise ValueError(f"unknown LLM error code: {code}")
        super().__init__(code)
        self.code = code

    @property
    def user_message(self) -> str:
        return ERROR_MESSAGES[self.code]
