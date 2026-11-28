"""Trades end to end: cash, positions, avg cost, snapshots, validation, tracked tickers."""

from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from .conftest import read_sse_events


def trade(client, ticker, quantity, side):
    return client.post("/api/portfolio/trade",
                       json={"ticker": ticker, "quantity": quantity, "side": side})


def portfolio(client):
    return client.get("/api/portfolio").json()


def position(client, ticker):
    return next((p for p in portfolio(client)["positions"] if p["ticker"] == ticker), None)


def snapshot_count(client):
    return len(client.get("/api/portfolio/history").json()["snapshots"])


def test_buy_moves_cash_into_position(client):
    before_snaps = snapshot_count(client)
    r = trade(client, "aapl", 10, "buy")
    assert r.status_code == 200, r.text
    body = r.json()
    t = body["trade"]
    assert t["ticker"] == "AAPL" and t["side"] == "buy" and t["quantity"] == 10.0
    assert t["price"] > 0
    assert t["total"] == round(t["price"] * 10, 2)
    assert t["executed_at"].endswith("+00:00")

    p = body["portfolio"]
    assert p["cash_balance"] == round(10000.0 - t["total"], 2)
    [pos] = p["positions"]
    assert pos["ticker"] == "AAPL"
    assert pos["quantity"] == 10.0
    assert pos["avg_cost"] == pytest.approx(t["price"])
    assert pos["market_value"] == pytest.approx(pos["quantity"] * pos["current_price"], abs=0.01)
    assert p["total_value"] == pytest.approx(p["cash_balance"] + p["positions_value"], abs=0.01)
    assert pos["weight_percent"] == pytest.approx(
        pos["market_value"] / p["total_value"] * 100, abs=0.01)

    # GET agrees with the trade response, and the trade recorded a snapshot.
    assert portfolio(client)["cash_balance"] == p["cash_balance"]
    assert snapshot_count(client) == before_snaps + 1


def test_weighted_avg_cost_and_partial_sell_keeps_avg(client):
    b1 = trade(client, "MSFT", 2, "buy").json()["trade"]
    b2 = trade(client, "MSFT", 3, "buy").json()["trade"]
    expected_avg = (2 * b1["price"] + 3 * b2["price"]) / 5
    pos = position(client, "MSFT")
    assert pos["quantity"] == 5.0
    assert pos["avg_cost"] == pytest.approx(expected_avg, abs=0.01)

    cash_before = portfolio(client)["cash_balance"]
    r = trade(client, "MSFT", 1.5, "sell")
    assert r.status_code == 200, r.text
    s = r.json()["trade"]
    after = r.json()["portfolio"]
    assert after["cash_balance"] == pytest.approx(cash_before + s["total"], abs=0.005)
    pos = position(client, "MSFT")
    assert pos["quantity"] == 3.5
    assert pos["avg_cost"] == pytest.approx(expected_avg, abs=0.01)


def test_full_sell_deletes_position(client):
    trade(client, "GOOGL", 0.5, "buy")
    r = trade(client, "GOOGL", 0.5, "sell")
    assert r.status_code == 200, r.text
    assert position(client, "GOOGL") is None
    assert portfolio(client)["positions"] == []


def test_fractional_quantity_rounded_to_four_decimals(client):
    r = trade(client, "NVDA", 1.234567, "buy")
    assert r.status_code == 200, r.text
    assert r.json()["trade"]["quantity"] == 1.2346
    assert position(client, "NVDA")["quantity"] == 1.2346


@pytest.mark.parametrize("quantity", [0, -1, 0.00001])
def test_non_positive_quantity_is_400(client, quantity):
    r = trade(client, "AAPL", quantity, "buy")
    assert r.status_code == 400, r.text
    assert isinstance(r.json()["detail"], str)
    assert portfolio(client)["cash_balance"] == 10000.0


def test_insufficient_cash_is_400_and_changes_nothing(client):
    snaps = snapshot_count(client)
    r = trade(client, "AAPL", 100000, "buy")
    assert r.status_code == 400
    assert "cash" in r.json()["detail"].lower()
    assert portfolio(client)["cash_balance"] == 10000.0
    assert portfolio(client)["positions"] == []
    assert snapshot_count(client) == snaps


def test_insufficient_shares_is_400(client):
    trade(client, "AAPL", 2, "buy")
    r = trade(client, "AAPL", 3, "sell")
    assert r.status_code == 400
    assert "shares" in r.json()["detail"].lower()
    assert position(client, "AAPL")["quantity"] == 2.0


def test_sell_without_position_is_400(client):
    r = trade(client, "TSLA", 1, "sell")
    assert r.status_code == 400


def test_untracked_ticker_has_no_price_400(client):
    r = trade(client, "ZZZZ", 1, "buy")
    assert r.status_code == 400
    assert "ZZZZ" in r.json()["detail"]


def test_malformed_ticker_is_400(client):
    assert trade(client, "12AB", 1, "buy").status_code == 400


@pytest.mark.parametrize("payload", [
    {"ticker": "AAPL", "quantity": 1, "side": "hold"},
    {"ticker": "AAPL", "quantity": "lots", "side": "buy"},
    {"ticker": "AAPL", "side": "buy"},
])
def test_schema_violations_are_422(client, payload):
    r = client.post("/api/portfolio/trade", json=payload)
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)


def test_position_keeps_ticker_tracked_after_watchlist_removal(client, server):
    """PLAN §6: removing a held ticker from the watchlist keeps it priced; selling out of a
    non-watched ticker stops tracking it."""
    assert trade(client, "TSLA", 1, "buy").status_code == 200
    assert client.delete("/api/watchlist/TSLA").status_code == 200

    # Still priced and streamed while held.
    assert "TSLA" in read_sse_events(server.base_url, count=1)[0]
    assert client.get("/api/health").json()["tracked_tickers"] == 10
    assert trade(client, "TSLA", 0.5, "buy").status_code == 200

    # Selling out removes it from the tracked set.
    assert trade(client, "TSLA", 1.5, "sell").status_code == 200
    assert client.get("/api/health").json()["tracked_tickers"] == 9
    assert "TSLA" not in read_sse_events(server.base_url, count=1)[0]
    assert trade(client, "TSLA", 1, "buy").status_code == 400


def test_selling_watched_ticker_keeps_it_tracked(client, server):
    trade(client, "META", 1, "buy")
    trade(client, "META", 1, "sell")
    assert client.get("/api/health").json()["tracked_tickers"] == 10
    assert "META" in read_sse_events(server.base_url, count=1)[0]


def test_concurrent_buys_never_overspend(server):
    """Twenty parallel buys worth ~20x the cash: cash must never go negative and must equal
    the starting cash minus exactly the executed trades."""
    price = next(i["price"] for i in httpx.get(f"{server.base_url}/api/watchlist",
                                                trust_env=False).json()["watchlist"]
                 if i["ticker"] == "AAPL")
    qty = round(10000 / price * 0.9, 4)  # each buy is ~90% of starting cash

    def buy(_):
        return httpx.post(f"{server.base_url}/api/portfolio/trade",
                          json={"ticker": "AAPL", "quantity": qty, "side": "buy"},
                          timeout=30, trust_env=False)

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(buy, range(20)))

    ok = [r.json()["trade"] for r in results if r.status_code == 200]
    rejected = [r for r in results if r.status_code == 400]
    assert len(ok) + len(rejected) == 20, [r.status_code for r in results]
    assert len(ok) == 1, f"{len(ok)} buys of ~90% cash each succeeded"

    p = httpx.get(f"{server.base_url}/api/portfolio", trust_env=False).json()
    assert p["cash_balance"] >= 0
    assert p["cash_balance"] == pytest.approx(10000.0 - sum(t["total"] for t in ok), abs=0.005)
    assert p["positions"][0]["quantity"] == pytest.approx(qty * len(ok))
