"""Chat flow through POST /api/chat with the LLM call replaced (no network)."""

from __future__ import annotations

import pytest

from app.llm import service
from app.llm.errors import (
    ERROR_MESSAGES,
    LLM_INVALID_RESPONSE,
    LLM_NOT_CONFIGURED,
    LLM_TIMEOUT,
    LLM_UNAVAILABLE,
    LLMError,
)
from app.llm.schema import LLMResponse, TradeAction, WatchlistAction


@pytest.fixture
def llm(monkeypatch, client):
    """Real (non-mock) mode with call_llm replaced. Set `llm.reply` to an LLMResponse or an
    LLMError; every prompt sent is recorded in `llm.prompts`."""
    monkeypatch.setenv("LLM_MOCK", "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    class Fake:
        def __init__(self) -> None:
            self.reply: LLMResponse | LLMError = reply()
            self.prompts: list[list[dict]] = []

    fake = Fake()

    async def call_llm(messages):
        fake.prompts.append(messages)
        if isinstance(fake.reply, LLMError):
            raise fake.reply
        return fake.reply

    monkeypatch.setattr(service, "call_llm", call_llm)
    return fake


def reply(message="ok", trades=(), changes=()):
    return LLMResponse(
        message=message,
        trades=[TradeAction(ticker=t, side=s, quantity=q) for t, s, q in trades],
        watchlist_changes=[WatchlistAction(ticker=t, action=a) for t, a in changes],
    )


def chat(client, message):
    r = client.post("/api/chat", json={"message": message})
    assert r.status_code == 200, r.text
    return r.json()


def test_partial_failures_are_independent_and_ordered(client, source, llm):
    source.set_price("AAPL", 100.0)
    llm.reply = reply(
        "Working on it",
        trades=[("AAPL", "buy", 1000), ("AAPL", "buy", 2), ("PYPL", "buy", 1), ("bad!", "buy", 1)],
        changes=[("PYPL", "add"), ("AAPL", "add"), ("zzz", "remove"), ("12", "add")],
    )
    a = chat(client, "do stuff")["assistant_message"]
    assert a["content"] == "Working on it"
    changes = a["actions"]["watchlist_changes"]
    assert [(c["ticker"], c["action"], c["status"]) for c in changes] == [
        ("PYPL", "add", "executed"),
        ("AAPL", "add", "rejected"),  # already watched
        ("ZZZ", "remove", "rejected"),  # not watched
        ("12", "add", "rejected"),  # invalid format: ticker kept as sent
    ]
    assert changes[0]["error"] is None
    assert changes[1]["error"] == "AAPL is already on the watchlist"
    assert changes[2]["error"] == "ZZZ is not on the watchlist"
    assert changes[3]["error"]

    trades = a["actions"]["trades"]
    assert [(t["ticker"], t["status"]) for t in trades] == [
        ("AAPL", "rejected"),
        ("AAPL", "executed"),
        ("PYPL", "executed"),  # priced because the watchlist add ran first
        ("bad!", "rejected"),
    ]
    assert trades[0]["error"].startswith("Insufficient cash") and trades[0]["price"] is None
    assert trades[1]["price"] == 100.0 and trades[1]["error"] is None
    assert a["actions"]["error"] is None

    p = client.get("/api/portfolio").json()
    assert sorted(x["ticker"] for x in p["positions"]) == ["AAPL", "PYPL"]

    stored = client.get("/api/chat/history").json()["messages"]
    assert stored[-1]["actions"] == a["actions"]


@pytest.mark.parametrize(
    "code", [LLM_TIMEOUT, LLM_UNAVAILABLE, LLM_INVALID_RESPONSE, LLM_NOT_CONFIGURED]
)
def test_llm_errors_are_200_with_friendly_text_and_stored(client, llm, code):
    llm.reply = LLMError(code)
    body = chat(client, "buy something")
    a = body["assistant_message"]
    assert a["content"] == ERROR_MESSAGES[code]
    assert a["actions"] == {"watchlist_changes": [], "trades": [], "error": code}
    msgs = client.get("/api/chat/history").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["actions"]["error"] == code


def test_missing_key_without_mock_is_not_configured(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "false")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    a = chat(client, "hi")["assistant_message"]
    assert a["actions"]["error"] == LLM_NOT_CONFIGURED


def test_prompt_has_context_history_and_action_summaries(client, source, llm):
    source.set_price("AAPL", 100.0)
    llm.reply = reply("Bought", trades=[("AAPL", "buy", 2), ("TSLA", "buy", 10000)])
    chat(client, "buy please")
    llm.reply = LLMError(LLM_UNAVAILABLE)
    chat(client, "this one fails")
    llm.reply = reply("fine")
    chat(client, "how am I doing?")

    prompt = llm.prompts[-1]
    assert prompt[0]["role"] == "system" and "FinAlly" in prompt[0]["content"]
    assert prompt[1]["role"] == "system"
    assert '"cash_balance":9800.0' in prompt[1]["content"]
    assert '"ticker":"AAPL","quantity":2.0' in prompt[1]["content"]
    rest = [(m["role"], m["content"]) for m in prompt[2:]]
    assert rest[0] == ("user", "buy please")
    assert rest[1] == ("assistant", "Bought")
    assert rest[2][0] == "system"
    assert rest[2][1].startswith("[actions] buy 2 AAPL: executed @ 100.0; buy 10000 TSLA: rejected")
    assert "Insufficient cash" in rest[2][1]
    # The failed exchange: the user message stays, the error reply is skipped.
    assert rest[3] == ("user", "this one fails")
    assert rest[4] == ("user", "how am I doing?")
    assert len(rest) == 5


def test_history_window_is_last_20_messages(client, llm):
    for i in range(12):
        chat(client, f"msg {i}")
    prompt = llm.prompts[-1]
    history = [m for m in prompt[2:-1] if m["role"] in ("user", "assistant")]
    assert len(history) == 20
    assert history[0]["content"] == "msg 1"  # msg 0 and its reply fell out of the window
    assert prompt[-1] == {"role": "user", "content": "msg 11"}


def test_message_is_trimmed_before_storing_and_sending(client, llm):
    body = chat(client, "   hi there  ")
    assert body["user_message"]["content"] == "hi there"
    assert llm.prompts[-1][-1]["content"] == "hi there"


def test_summarize_actions():
    assert service.summarize_actions(None) is None
    assert service.summarize_actions(service.empty_actions()) is None
    text = service.summarize_actions(
        {
            "watchlist_changes": [
                {"ticker": "X", "action": "add", "status": "rejected", "error": "nope"}
            ],
            "trades": [
                {
                    "ticker": "A",
                    "side": "sell",
                    "quantity": 1.5,
                    "status": "executed",
                    "price": 10.0,
                    "error": None,
                }
            ],
            "error": None,
        }
    )
    assert text == "[actions] add X (watchlist): rejected (nope); sell 1.5 A: executed @ 10.0"
