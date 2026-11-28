"""Mock mode rules (planning/API_CHAT.md, section Mock mode)."""

from __future__ import annotations

import pytest

from app.llm.errors import LLM_UNAVAILABLE, LLMError
from app.llm.mock import GREETING, is_mock_mode, mock_reply

PREFIX = "Mock mode: processing your request."


def test_greeting_when_nothing_matches():
    r = mock_reply("  hello  ")
    assert r.message == GREETING
    assert r.trades == [] and r.watchlist_changes == []


@pytest.mark.parametrize(
    ("text", "content", "changes", "trades"),
    [
        ("Buy some apple", f"{PREFIX} Buying 1 share of AAPL.", [], [("AAPL", "buy", 1)]),
        ("add PYPL", f"{PREFIX} Adding PYPL to your watchlist.", [("PYPL", "add")], []),
        (
            "remove nflx and sell",
            f"{PREFIX} Removing NFLX from your watchlist. Selling 1 share of AAPL.",
            [("NFLX", "remove")],
            [("AAPL", "sell", 1)],
        ),
        (
            "SELL then BUY, remove x and ADD brk.b, add z",
            (
                f"{PREFIX} Adding BRK.B to your watchlist. Removing X from your watchlist. "
                "Buying 1 share of AAPL. Selling 1 share of AAPL."
            ),
            [("BRK.B", "add"), ("X", "remove")],
            [("AAPL", "buy", 1), ("AAPL", "sell", 1)],
        ),
    ],
)
def test_rules(text, content, changes, trades):
    r = mock_reply(text)
    assert r.message == content
    assert [(c.ticker, c.action) for c in r.watchlist_changes] == changes
    assert [(t.ticker, t.side, t.quantity) for t in r.trades] == trades


def test_word_boundaries():
    assert mock_reply("buyer seller address").message == GREETING


def test_deterministic():
    assert mock_reply("buy and add MSFT") == mock_reply("buy and add MSFT")


def test_mock_error_wins_over_actions():
    with pytest.raises(LLMError) as exc:
        mock_reply("buy, then Mock Error please")
    assert exc.value.code == LLM_UNAVAILABLE


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), (" TRUE ", True), ("false", False), ("", False), ("1", False)],
)
def test_is_mock_mode(monkeypatch, value, expected):
    monkeypatch.setenv("LLM_MOCK", value)
    assert is_mock_mode() is expected


def test_is_mock_mode_unset(monkeypatch):
    monkeypatch.delenv("LLM_MOCK", raising=False)
    assert is_mock_mode() is False
