"""Fixtures: the real app on a temp SQLite DB with a deterministic fake market source."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as main_module
from app.market import MarketDataSource, PriceCache, normalize_ticker
from app.services.state import get_state

DEFAULT_PRICE = 100.0


class FakeSource(MarketDataSource):
    """Prices every tracked ticker at a fixed value; tests change prices via set_price()."""

    def __init__(self, price_cache: PriceCache) -> None:
        self.cache = price_cache
        self.tickers: list[str] = []
        self.prices: dict[str, float] = {}
        self.removed: list[str] = []
        self.stopped = False

    def set_price(self, ticker: str, price: float) -> None:
        self.prices[ticker] = price
        self.cache.update(ticker, price)

    async def start(self, tickers: list[str]) -> None:
        for t in tickers:
            await self.add_ticker(t)

    async def stop(self) -> None:
        self.stopped = True

    async def add_ticker(self, ticker: str) -> None:
        ticker = normalize_ticker(ticker)
        if ticker not in self.tickers:
            self.tickers.append(ticker)
            self.cache.update(ticker, self.prices.get(ticker, DEFAULT_PRICE))

    async def remove_ticker(self, ticker: str) -> None:
        ticker = normalize_ticker(ticker)
        if ticker in self.tickers:
            self.tickers.remove(ticker)
            self.removed.append(ticker)
            self.cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return list(self.tickers)


@pytest.fixture
def make_app(monkeypatch):
    """Build the real app with FakeSource: make_app(db_path, static_dir)."""
    monkeypatch.setattr(main_module, "create_market_data_source", FakeSource)

    def _make(db_path: Path, static_dir: Path) -> FastAPI:
        return main_module.create_app(db_path=db_path, static_dir=static_dir)

    return _make


@pytest.fixture
def client(tmp_path, make_app) -> Iterator[TestClient]:
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>FinAlly</html>", encoding="utf-8")
    (static / "app.js").write_text("console.log(1)", encoding="utf-8")
    with TestClient(make_app(tmp_path / "test.db", static)) as c:
        yield c


@pytest.fixture
def source(client) -> FakeSource:
    return get_state().source  # type: ignore[return-value]
