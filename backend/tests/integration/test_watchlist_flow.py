"""Watchlist CRUD through the API, and its effect on the tracked/streamed tickers."""

import pytest

from .conftest import DEFAULT_TICKERS, read_sse_events, wait_for


def tickers(client):
    return [i["ticker"] for i in client.get("/api/watchlist").json()["watchlist"]]


def test_add_normalises_prices_and_streams_ticker(client, server):
    r = client.post("/api/watchlist", json={"ticker": "  pypl "})
    assert r.status_code == 201
    item = r.json()
    assert item["ticker"] == "PYPL"
    assert item["price"] is not None and item["price"] > 0
    assert set(item) >= {
        "price",
        "previous_price",
        "change_percent",
        "day_change_percent",
        "direction",
        "added_at",
    }

    assert tickers(client) == DEFAULT_TICKERS + ["PYPL"]
    assert client.get("/api/health").json()["tracked_tickers"] == 11
    assert "PYPL" in read_sse_events(server.base_url, count=1)[0]


def test_duplicate_add_is_409(client):
    r = client.post("/api/watchlist", json={"ticker": "aapl"})
    assert r.status_code == 409
    assert isinstance(r.json()["detail"], str) and "AAPL" in r.json()["detail"]


@pytest.mark.parametrize("bad", ["12AB", "", "TOOLONGTICKER", "A B", "$$$"])
def test_malformed_ticker_add_is_400(client, bad):
    r = client.post("/api/watchlist", json={"ticker": bad})
    assert r.status_code == 400, r.text
    assert isinstance(r.json()["detail"], str)
    assert tickers(client) == DEFAULT_TICKERS


def test_add_without_body_field_is_422(client):
    r = client.post("/api/watchlist", json={})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)


def test_remove_then_remove_again(client, server):
    r = client.delete("/api/watchlist/nflx")
    assert r.status_code == 200
    assert r.json() == {"ticker": "NFLX", "removed": True}
    assert "NFLX" not in tickers(client)

    # Not tracked any more: dropped from the stream and from the source.
    assert client.get("/api/health").json()["tracked_tickers"] == 9
    wait_for(
        lambda: "NFLX" not in read_sse_events(server.base_url, count=1)[0],
        message="NFLX still streamed after removal",
    )

    r = client.delete("/api/watchlist/NFLX")
    assert r.status_code == 404
    assert "NFLX" in r.json()["detail"]


def test_remove_malformed_ticker_is_400(client):
    r = client.delete("/api/watchlist/12AB")
    assert r.status_code == 400


def test_readd_after_remove_goes_to_end(client):
    assert client.delete("/api/watchlist/AAPL").status_code == 200
    assert client.post("/api/watchlist", json={"ticker": "AAPL"}).status_code == 201
    assert tickers(client) == DEFAULT_TICKERS[1:] + ["AAPL"]
