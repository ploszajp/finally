"""API contract edge cases: unknown /api paths, non-finite quantities, snapshot timing."""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.services import trading
from app.services.errors import TradeError


def _raw_trade(client, quantity_literal: str):
    body = f'{{"ticker": "AAPL", "quantity": {quantity_literal}, "side": "buy"}}'
    return client.post(
        "/api/portfolio/trade", content=body, headers={"content-type": "application/json"}
    )


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_unknown_api_path_is_404_for_every_method(client, method):
    r = client.request(method, "/api/does/not/exist")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}


def test_known_api_path_with_wrong_method_is_405(client):
    r = client.put("/api/watchlist")
    assert r.status_code == 405
    assert r.json() == {"detail": "Method Not Allowed"}
    assert client.post("/api/health").status_code == 405
    assert client.post("/api/watchlist/AAPL").status_code == 405


def test_bare_api_path_is_404(client):
    assert client.get("/api").status_code == 404
    assert client.post("/api").status_code == 405  # SPA route is GET-only


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_quantity_is_422(client, literal):
    r = _raw_trade(client, literal)
    assert r.status_code == 422  # FastAPI's default handler would crash with a 500 here
    assert isinstance(r.json()["detail"], list)
    assert client.get("/api/portfolio").json()["cash_balance"] == 10000.0


def test_absurd_quantity_is_400_with_readable_message(client):
    r = _raw_trade(client, "1e308")
    assert r.status_code == 400
    assert r.json() == {"detail": "Quantity is too large"}


def test_service_rejects_non_finite_quantity(client, source):
    # The chat service calls the service directly, bypassing request validation.
    for q in (float("inf"), float("nan"), "inf"):
        with pytest.raises(TradeError):
            asyncio.run(trading.execute_trade("AAPL", "buy", q))


def test_snapshot_failure_does_not_fail_committed_trade(client, source, monkeypatch):
    def boom():
        raise RuntimeError("disk full")

    monkeypatch.setattr(trading, "record_snapshot", boom)
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})
    assert r.status_code == 200
    assert client.get("/api/portfolio").json()["positions"][0]["ticker"] == "AAPL"


def test_periodic_snapshot_task(tmp_path, make_app):
    make_app(tmp_path / "unused.db", tmp_path)  # installs FakeSource
    app = main_module.create_app(
        db_path=tmp_path / "x.db", static_dir=tmp_path, snapshot_interval=0.05
    )
    with TestClient(app) as c:
        deadline = time.monotonic() + 5
        while len(c.get("/api/portfolio/history").json()["snapshots"]) < 3:
            assert time.monotonic() < deadline, "periodic snapshots not recorded"
            time.sleep(0.05)
