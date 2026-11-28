"""Chat with LLM_MOCK=true: deterministic replies, real action execution, persistence."""

import httpx
import pytest

GREETING = (
    "Hello from FinAlly (mock mode). I can buy or sell AAPL and add or remove watchlist tickers."
)
UNAVAILABLE = "The AI assistant is unavailable right now. Please try again in a moment."


def chat(client, message):
    r = client.post("/api/chat", json={"message": message})
    assert r.status_code == 200, r.text
    return r.json()


def watchlist(client):
    return [i["ticker"] for i in client.get("/api/watchlist").json()["watchlist"]]


def portfolio(client):
    return client.get("/api/portfolio").json()


def test_plain_message_gets_greeting_and_no_actions(client):
    body = chat(client, "  hello  ")
    user, assistant = body["user_message"], body["assistant_message"]
    assert user["role"] == "user"
    assert user["content"] == "hello"
    assert user["actions"] is None
    assert assistant["role"] == "assistant"
    assert assistant["content"] == GREETING
    assert assistant["actions"] == {"watchlist_changes": [], "trades": [], "error": None}
    assert assistant["created_at"].endswith("+00:00")


def test_buy_executes_real_trade(client):
    body = chat(client, "Buy some apple")
    a = body["assistant_message"]
    assert a["content"] == "Mock mode: processing your request. Buying 1 share of AAPL."
    [t] = a["actions"]["trades"]
    assert t["ticker"] == "AAPL" and t["side"] == "buy" and t["quantity"] == 1
    assert t["status"] == "executed" and t["error"] is None and t["price"] > 0

    p = portfolio(client)
    assert p["cash_balance"] == round(10000.0 - t["price"], 2)
    assert [(x["ticker"], x["quantity"]) for x in p["positions"]] == [("AAPL", 1.0)]
    # A chat trade records a snapshot like a manual trade does.
    assert len(client.get("/api/portfolio/history").json()["snapshots"]) >= 2


def test_add_ticker_via_chat_and_duplicate_rejected(client):
    a = chat(client, "add pypl")["assistant_message"]
    assert a["content"] == "Mock mode: processing your request. Adding PYPL to your watchlist."
    assert a["actions"]["watchlist_changes"] == [
        {"ticker": "PYPL", "action": "add", "status": "executed", "error": None}
    ]
    assert watchlist(client)[-1] == "PYPL"

    a = chat(client, "add PYPL")["assistant_message"]
    [change] = a["actions"]["watchlist_changes"]
    assert change["status"] == "rejected"
    assert "PYPL" in change["error"]
    assert watchlist(client).count("PYPL") == 1


def test_remove_and_sell_execute_in_order_and_independently(client):
    a = chat(client, "remove nflx and sell")["assistant_message"]
    assert a["content"] == (
        "Mock mode: processing your request. Removing NFLX from your watchlist. "
        "Selling 1 share of AAPL."
    )
    [change] = a["actions"]["watchlist_changes"]
    assert change == {"ticker": "NFLX", "action": "remove", "status": "executed", "error": None}
    # No AAPL held: the sell is rejected but the removal still happened.
    [t] = a["actions"]["trades"]
    assert t["status"] == "rejected" and t["price"] is None
    assert t["error"]
    assert "NFLX" not in watchlist(client)
    assert portfolio(client)["cash_balance"] == 10000.0


def test_buy_then_sell_in_one_message(client):
    a = chat(client, "buy and then sell")["assistant_message"]
    trades = a["actions"]["trades"]
    assert [(t["side"], t["status"]) for t in trades] == [
        ("buy", "executed"),
        ("sell", "executed"),
    ]
    assert portfolio(client)["positions"] == []


def test_mock_error_returns_friendly_failure(client):
    body = chat(client, "please trigger a MOCK ERROR, and buy")
    a = body["assistant_message"]
    assert a["content"] == UNAVAILABLE
    assert a["actions"] == {"watchlist_changes": [], "trades": [], "error": "llm_unavailable"}
    assert portfolio(client)["positions"] == []  # no actions on failure


def test_history_persists_both_messages_with_results(client):
    chat(client, "hello")
    chat(client, "buy")
    chat(client, "mock error")
    msgs = client.get("/api/chat/history").json()["messages"]
    assert [(m["role"], m["content"]) for m in msgs] == [
        ("user", "hello"),
        ("assistant", GREETING),
        ("user", "buy"),
        ("assistant", "Mock mode: processing your request. Buying 1 share of AAPL."),
        ("user", "mock error"),
        ("assistant", UNAVAILABLE),
    ]
    assert msgs[3]["actions"]["trades"][0]["status"] == "executed"
    assert msgs[5]["actions"]["error"] == "llm_unavailable"
    assert all(m["actions"] is None for m in msgs if m["role"] == "user")

    limited = client.get("/api/chat/history", params={"limit": 2}).json()["messages"]
    assert [m["content"] for m in limited] == ["mock error", UNAVAILABLE]


@pytest.mark.parametrize(
    "payload", [{"message": ""}, {"message": "   "}, {"message": "x" * 2001}, {}]
)
def test_invalid_chat_requests_are_422_and_not_stored(client, payload):
    r = client.post("/api/chat", json=payload)
    assert r.status_code == 422
    assert client.get("/api/chat/history").json()["messages"] == []


@pytest.mark.parametrize("limit", [0, 201])
def test_history_limit_out_of_range_is_422(client, limit):
    assert client.get("/api/chat/history", params={"limit": limit}).status_code == 422


def test_without_mock_and_without_key_chat_is_not_configured(server_factory):
    s = server_factory(LLM_MOCK="false", OPENROUTER_API_KEY="")
    with httpx.Client(base_url=s.base_url, trust_env=False, timeout=10) as c:
        r = c.post("/api/chat", json={"message": "buy"})
        assert r.status_code == 200
        a = r.json()["assistant_message"]
        assert a["actions"] == {
            "watchlist_changes": [],
            "trades": [],
            "error": "llm_not_configured",
        }
        assert "OPENROUTER_API_KEY" in a["content"]
        # The rest of the app works without a key.
        assert c.get("/api/portfolio").json()["cash_balance"] == 10000.0
        r = c.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})
        assert r.status_code == 200
