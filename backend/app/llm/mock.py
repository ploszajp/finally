"""Deterministic replies for LLM_MOCK=true (rules in planning/API_CHAT.md "Mock mode")."""

from __future__ import annotations

import os
import re

from .errors import LLM_UNAVAILABLE, LLMError
from .schema import LLMResponse, TradeAction, WatchlistAction

GREETING = (
    "Hello from FinAlly (mock mode). I can buy or sell AAPL and add or remove watchlist tickers."
)
PREFIX = "Mock mode: processing your request."

_ADD = re.compile(r"\badd\s+([A-Za-z][A-Za-z.\-]{0,9})\b", re.IGNORECASE)
_REMOVE = re.compile(r"\bremove\s+([A-Za-z][A-Za-z.\-]{0,9})\b", re.IGNORECASE)
_BUY = re.compile(r"\bbuy\b", re.IGNORECASE)
_SELL = re.compile(r"\bsell\b", re.IGNORECASE)
_ERROR = re.compile(r"mock error", re.IGNORECASE)

MOCK_TICKER = "AAPL"


def is_mock_mode() -> bool:
    return os.environ.get("LLM_MOCK", "").strip().lower() == "true"


def mock_reply(user_message: str) -> LLMResponse:
    """Pure function of the message. Raises LLMError(llm_unavailable) for "mock error"."""
    text = user_message.strip()
    if _ERROR.search(text):
        raise LLMError(LLM_UNAVAILABLE)

    changes: list[WatchlistAction] = []
    trades: list[TradeAction] = []
    sentences: list[str] = []

    if m := _ADD.search(text):
        ticker = m.group(1).upper()
        changes.append(WatchlistAction(ticker=ticker, action="add"))
        sentences.append(f"Adding {ticker} to your watchlist.")
    if m := _REMOVE.search(text):
        ticker = m.group(1).upper()
        changes.append(WatchlistAction(ticker=ticker, action="remove"))
        sentences.append(f"Removing {ticker} from your watchlist.")
    if _BUY.search(text):
        trades.append(TradeAction(ticker=MOCK_TICKER, side="buy", quantity=1))
        sentences.append(f"Buying 1 share of {MOCK_TICKER}.")
    if _SELL.search(text):
        trades.append(TradeAction(ticker=MOCK_TICKER, side="sell", quantity=1))
        sentences.append(f"Selling 1 share of {MOCK_TICKER}.")

    message = " ".join([PREFIX, *sentences]) if sentences else GREETING
    return LLMResponse(message=message, trades=trades, watchlist_changes=changes)
