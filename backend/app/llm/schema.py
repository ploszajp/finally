"""Structured output schema for the LLM and tolerant parsing of its replies."""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError


class TradeAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    side: Literal["buy", "sell"]
    quantity: float


class WatchlistAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    action: Literal["add", "remove"]


class LLMResponse(BaseModel):
    """What the LLM must return. Every field is required (strict structured outputs);
    unused arrays are empty."""

    model_config = ConfigDict(extra="forbid")

    message: str
    trades: list[TradeAction]
    watchlist_changes: list[WatchlistAction]


class InvalidLLMResponseError(ValueError):
    """The reply could not be turned into an LLMResponse."""


_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def parse_llm_response(content: str | None) -> LLMResponse:
    """Parse the model's text into an LLMResponse.

    Tolerates a Markdown code fence around the JSON and missing (but not malformed) action
    arrays. Anything else raises InvalidLLMResponseError.
    """
    if not content or not content.strip():
        raise InvalidLLMResponseError("empty response")
    text = content.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise InvalidLLMResponseError(f"not JSON: {e.msg}") from None
    if not isinstance(data, dict):
        raise InvalidLLMResponseError("JSON is not an object")
    for key in ("trades", "watchlist_changes"):
        if data.get(key) is None:
            data[key] = []
    try:
        return LLMResponse.model_validate(data)
    except ValidationError as e:
        raise InvalidLLMResponseError(f"schema mismatch ({e.error_count()} errors)") from None
