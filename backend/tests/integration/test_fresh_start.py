"""A brand-new database: seed data, first snapshot, live prices, error formats."""

from .conftest import DEFAULT_TICKERS, read_sse_events

PRICE_FIELDS = {
    "ticker",
    "price",
    "previous_price",
    "timestamp",
    "change",
    "change_percent",
    "direction",
    "reference_price",
    "day_change_percent",
}


def test_health_reports_simulator(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["market_data_source"] == "simulator"
    assert body["tracked_tickers"] == 10
    assert body["last_success_at"] is None
    assert body["last_error"] is None


def test_default_watchlist_in_seed_order_with_prices(client):
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    items = r.json()["watchlist"]
    assert [i["ticker"] for i in items] == DEFAULT_TICKERS
    for item in items:
        assert item["price"] is not None and item["price"] > 0, item
        assert item["direction"] in {"up", "down", "flat"}
        assert isinstance(item["day_change_percent"], (int, float))
        assert item["added_at"].endswith("+00:00")


def test_fresh_portfolio_is_ten_thousand_cash(client):
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    assert r.json() == {
        "cash_balance": 10000.0,
        "positions_value": 0.0,
        "total_value": 10000.0,
        "unrealized_pnl": 0.0,
        "unrealized_pnl_percent": 0.0,
        "positions": [],
    }


def test_startup_records_first_snapshot(client):
    r = client.get("/api/portfolio/history")
    assert r.status_code == 200
    snapshots = r.json()["snapshots"]
    assert len(snapshots) >= 1
    assert snapshots[0]["total_value"] == 10000.0
    assert snapshots[0]["recorded_at"].endswith("+00:00")


def test_chat_history_starts_empty(client):
    r = client.get("/api/chat/history")
    assert r.status_code == 200
    assert r.json() == {"messages": []}


def test_sse_first_event_is_full_snapshot_and_prices_move(server):
    events = read_sse_events(server.base_url, count=4, timeout=15)
    first = events[0]
    assert set(first) == set(DEFAULT_TICKERS)
    for ticker, update in first.items():
        assert PRICE_FIELDS <= set(update), update
        assert update["ticker"] == ticker
        assert update["price"] > 0
        # Unix epoch seconds, not milliseconds.
        assert 1.6e9 < update["timestamp"] < 1e10
    # Every event is the complete set, and the stream actually streams.
    assert all(set(e) == set(DEFAULT_TICKERS) for e in events)
    stamps = {max(u["timestamp"] for u in e.values()) for e in events}
    assert len(stamps) > 1, "SSE events did not change over time"


def test_unknown_api_path_is_json_404(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}
