"""State survives a restart on the same database file; seeding is not repeated."""

import httpx

from .conftest import DEFAULT_TICKERS


def test_restart_keeps_portfolio_watchlist_chat_and_history(server_factory, tmp_path):
    db = tmp_path / "persist.db"
    first = server_factory(db)
    with httpx.Client(base_url=first.base_url, trust_env=False, timeout=10) as c:
        bought = c.post(
            "/api/portfolio/trade", json={"ticker": "JPM", "quantity": 3, "side": "buy"}
        ).json()
        assert c.delete("/api/watchlist/V").status_code == 200
        assert c.post("/api/watchlist", json={"ticker": "PYPL"}).status_code == 201
        assert c.delete("/api/watchlist/JPM").status_code == 200  # held, not watched
        c.post("/api/chat", json={"message": "hello"})
        snaps_before = len(c.get("/api/portfolio/history").json()["snapshots"])
    first.stop()

    second = server_factory(db)
    with httpx.Client(base_url=second.base_url, trust_env=False, timeout=10) as c:
        p = c.get("/api/portfolio").json()
        assert p["cash_balance"] == bought["portfolio"]["cash_balance"]
        [pos] = p["positions"]
        assert (pos["ticker"], pos["quantity"]) == ("JPM", 3.0)
        assert pos["avg_cost"] == bought["trade"]["price"]

        watch = [i["ticker"] for i in c.get("/api/watchlist").json()["watchlist"]]
        expected = [t for t in DEFAULT_TICKERS if t not in ("V", "JPM")] + ["PYPL"]
        assert watch == expected, "seed data re-applied or watchlist lost on restart"

        # Held-but-unwatched JPM is tracked again after restart (watchlist + positions).
        assert c.get("/api/health").json()["tracked_tickers"] == len(expected) + 1
        assert pos["current_price"] > 0
        r = c.post("/api/portfolio/trade", json={"ticker": "JPM", "quantity": 3, "side": "sell"})
        assert r.status_code == 200, r.text

        assert len(c.get("/api/chat/history").json()["messages"]) == 2
        # Restart adds a startup snapshot on top of the old ones.
        assert len(c.get("/api/portfolio/history").json()["snapshots"]) >= snaps_before + 1
