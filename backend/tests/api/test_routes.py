from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import DEFAULT_TICKERS
from app.services.state import get_state


def _trade(client, **kw):
    body = {"ticker": "AAPL", "quantity": 1, "side": "buy", **kw}
    return client.post("/api/portfolio/trade", json=body)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["market_data_source"] == "simulator"
    assert body["tracked_tickers"] == 10
    assert body["last_success_at"] is None
    assert body["last_error"] is None


def test_fresh_portfolio(client):
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


def test_initial_snapshot_recorded(client):
    snaps = client.get("/api/portfolio/history").json()["snapshots"]
    assert len(snaps) == 1
    assert snaps[0]["total_value"] == 10000.0
    assert snaps[0]["recorded_at"]


def test_history_limit_validation(client):
    assert client.get("/api/portfolio/history?limit=0").status_code == 422
    assert client.get("/api/portfolio/history?limit=1").status_code == 200


def test_watchlist_default(client):
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    items = r.json()["watchlist"]
    assert [i["ticker"] for i in items] == list(DEFAULT_TICKERS)
    assert items[0]["price"] == 100.0
    assert set(items[0]) == {
        "ticker",
        "price",
        "previous_price",
        "change_percent",
        "day_change_percent",
        "direction",
        "added_at",
    }


def test_watchlist_add_and_remove(client, source):
    r = client.post("/api/watchlist", json={"ticker": " pypl "})
    assert r.status_code == 201
    assert r.json()["ticker"] == "PYPL"
    assert r.json()["price"] == 100.0
    assert "PYPL" in source.get_tickers()

    r = client.post("/api/watchlist", json={"ticker": "PYPL"})
    assert r.status_code == 409
    assert r.json() == {"detail": "PYPL is already on the watchlist"}

    r = client.delete("/api/watchlist/pypl")
    assert r.status_code == 200
    assert r.json() == {"ticker": "PYPL", "removed": True}
    assert "PYPL" not in source.get_tickers()

    r = client.delete("/api/watchlist/PYPL")
    assert r.status_code == 404
    assert r.json() == {"detail": "PYPL is not on the watchlist"}


def test_watchlist_bad_ticker(client):
    r = client.post("/api/watchlist", json={"ticker": "12AB"})
    assert r.status_code == 400
    assert isinstance(r.json()["detail"], str)
    assert client.delete("/api/watchlist/1ab").status_code == 400
    assert client.post("/api/watchlist", json={}).status_code == 422


def test_remove_watchlist_keeps_tracking_when_position_open(client, source):
    assert _trade(client).status_code == 200
    assert client.delete("/api/watchlist/AAPL").status_code == 200
    assert "AAPL" in source.get_tickers()
    # Selling out of a ticker that is not on the watchlist stops tracking it.
    assert _trade(client, side="sell").status_code == 200
    assert "AAPL" not in source.get_tickers()


def test_full_sell_of_watched_ticker_keeps_tracking(client, source):
    _trade(client)
    _trade(client, side="sell")
    assert "AAPL" in source.get_tickers()


def test_buy_trade_response(client, source):
    source.set_price("AAPL", 190.5)
    r = _trade(client, ticker="aapl", quantity=10, side="BUY")
    assert r.status_code == 200
    body = r.json()
    t = body["trade"]
    assert (t["ticker"], t["side"], t["quantity"], t["price"], t["total"]) == (
        "AAPL",
        "buy",
        10.0,
        190.5,
        1905.0,
    )
    assert t["id"] and t["executed_at"]
    p = body["portfolio"]
    assert p["cash_balance"] == 8095.0
    assert p["positions"][0]["ticker"] == "AAPL"
    assert p["positions"][0]["avg_cost"] == 190.5
    assert p["total_value"] == 10000.0
    # A snapshot is recorded after each trade.
    assert len(client.get("/api/portfolio/history").json()["snapshots"]) == 2


def test_portfolio_pnl_math(client, source):
    source.set_price("AAPL", 100.0)
    _trade(client, quantity=10)
    source.set_price("AAPL", 110.0)
    p = client.get("/api/portfolio").json()
    pos = p["positions"][0]
    assert pos["current_price"] == 110.0
    assert pos["market_value"] == 1100.0
    assert pos["unrealized_pnl"] == 100.0
    assert pos["pnl_percent"] == 10.0
    assert pos["weight_percent"] == round(1100 / 10100 * 100, 2)
    assert p["cash_balance"] == 9000.0
    assert p["total_value"] == 10100.0
    assert p["unrealized_pnl"] == 100.0
    assert p["unrealized_pnl_percent"] == 10.0


def test_trade_errors(client):
    r = _trade(client, quantity=1000)
    assert r.status_code == 400
    assert r.json() == {"detail": "Insufficient cash: need $100,000.00, have $10,000.00"}
    r = _trade(client, side="sell")
    assert r.status_code == 400
    assert r.json()["detail"].startswith("Insufficient shares")
    assert _trade(client, quantity=0).status_code == 400
    assert _trade(client, quantity=-1).status_code == 400
    assert _trade(client, quantity=0.00001).status_code == 400  # rounds to 0
    r = _trade(client, ticker="ZZZZ")
    assert r.status_code == 400
    assert r.json() == {"detail": "No price available for ZZZZ. Add it to the watchlist first."}
    assert _trade(client, ticker="1X").status_code == 400
    assert _trade(client, side="short").status_code == 422
    assert client.post("/api/portfolio/trade", json={"ticker": "AAPL"}).status_code == 422
    assert client.get("/api/portfolio").json()["cash_balance"] == 10000.0


def test_unknown_api_path_is_json_404(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}


def test_static_and_spa_fallback(client):
    assert client.get("/").text == "<html>FinAlly</html>"
    assert client.get("/app.js").text == "console.log(1)"
    assert client.get("/some/client/route").text == "<html>FinAlly</html>"
    assert client.get("/..%2F..%2Ftest.db").text == "<html>FinAlly</html>"


def test_starts_without_static_dir(tmp_path, make_app):
    with TestClient(make_app(tmp_path / "x.db", tmp_path / "missing")) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/").status_code == 404


def test_shutdown_stops_source(tmp_path, make_app):
    with TestClient(make_app(tmp_path / "x.db", tmp_path)):
        src = get_state().source
    assert src.stopped


def test_restart_tracks_positions_off_watchlist(tmp_path, make_app):
    db = tmp_path / "x.db"
    with TestClient(make_app(db, tmp_path)) as c:
        c.post("/api/watchlist", json={"ticker": "PYPL"})
        _trade(c, ticker="PYPL", quantity=2)
        c.delete("/api/watchlist/PYPL")
    with TestClient(make_app(db, tmp_path)) as c:
        assert "PYPL" in get_state().source.get_tickers()
        assert c.get("/api/portfolio").json()["positions"][0]["ticker"] == "PYPL"
