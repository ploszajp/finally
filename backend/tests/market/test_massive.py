import sys
import types
from unittest.mock import MagicMock

import pytest

from app.market.cache import PriceCache
from app.market.massive_client import MassiveDataSource


def snap(ticker, price, ts_ms):
    s = MagicMock()
    s.ticker = ticker
    s.last_trade.price = price
    s.last_trade.timestamp = ts_ms
    return s


def make(tickers=("AAPL", "GOOGL")):
    cache = PriceCache()
    src = MassiveDataSource("key", cache, poll_interval=60.0)
    src._tickers = list(tickers)
    src._client = object()  # truthy; _fetch_snapshots is patched
    return cache, src


@pytest.fixture
def fake_massive(monkeypatch):
    """Install a fake `massive` package so tests don't need the real one."""
    client = MagicMock()
    client.get_snapshot_all.return_value = [snap("AAPL", 190.5, 1707580800000)]
    mod = types.ModuleType("massive")
    mod.RESTClient = MagicMock(return_value=client)
    rest = types.ModuleType("massive.rest")
    models = types.ModuleType("massive.rest.models")
    models.SnapshotMarketType = types.SimpleNamespace(STOCKS="stocks")
    mod.rest = rest
    rest.models = models
    monkeypatch.setitem(sys.modules, "massive", mod)
    monkeypatch.setitem(sys.modules, "massive.rest", rest)
    monkeypatch.setitem(sys.modules, "massive.rest.models", models)
    return mod, client


async def test_poll_updates_cache(monkeypatch):
    cache, src = make()
    monkeypatch.setattr(
        src, "_fetch_snapshots",
        lambda: [snap("AAPL", 190.5, 1707580800000), snap("GOOGL", 175.25, 1707580800000)],
    )
    await src._poll_once()
    assert cache.get_price("AAPL") == 190.5
    assert cache.get_price("GOOGL") == 175.25


async def test_timestamp_ms_to_seconds(monkeypatch):
    cache, src = make()
    monkeypatch.setattr(src, "_fetch_snapshots", lambda: [snap("AAPL", 1.0, 1707580800000)])
    await src._poll_once()
    assert cache.get("AAPL").timestamp == 1707580800.0


async def test_malformed_snapshot_skipped(monkeypatch):
    cache, src = make(["AAPL", "BAD"])
    bad = MagicMock()
    bad.ticker = "BAD"
    bad.last_trade = None
    monkeypatch.setattr(src, "_fetch_snapshots", lambda: [bad, snap("AAPL", 190.5, 1)])
    await src._poll_once()
    assert cache.get_price("AAPL") == 190.5
    assert cache.get_price("BAD") is None


async def test_api_error_does_not_crash(monkeypatch):
    cache, src = make()

    def boom():
        raise RuntimeError("network")

    monkeypatch.setattr(src, "_fetch_snapshots", boom)
    await src._poll_once()
    assert len(cache) == 0


async def test_keeps_last_prices_on_error(monkeypatch):
    cache, src = make()
    cache.update("AAPL", 100.0)

    def boom():
        raise RuntimeError("429")

    monkeypatch.setattr(src, "_fetch_snapshots", boom)
    await src._poll_once()
    assert cache.get_price("AAPL") == 100.0


async def test_poll_noop_without_tickers_or_client():
    cache = PriceCache()
    src = MassiveDataSource("k", cache)
    await src._poll_once()  # no client
    src._client = object()
    await src._poll_once()  # no tickers
    assert len(cache) == 0


async def test_add_remove_ticker():
    cache, src = make(["AAPL"])
    await src.add_ticker(" pypl ")
    await src.add_ticker("PYPL")
    assert src.get_tickers() == ["AAPL", "PYPL"]
    cache.update("PYPL", 50.0)
    await src.remove_ticker("pypl")
    assert src.get_tickers() == ["AAPL"]
    assert cache.get("PYPL") is None


async def test_start_polls_immediately_and_stop(fake_massive):
    _, client = fake_massive
    cache = PriceCache()
    src = MassiveDataSource("key", cache, poll_interval=60.0)
    await src.start(["aapl", "AAPL", "GOOGL"])
    assert src.get_tickers() == ["AAPL", "GOOGL"]
    assert cache.get_price("AAPL") == 190.5
    kwargs = client.get_snapshot_all.call_args.kwargs
    assert kwargs["tickers"] == ["AAPL", "GOOGL"]
    assert kwargs["market_type"] == "stocks"
    assert src._task is not None
    await src.stop()
    await src.stop()
    assert src._task is None and src._client is None


async def test_poll_loop_repolls(fake_massive):
    cache = PriceCache()
    src = MassiveDataSource("key", cache, poll_interval=0.02)
    await src.start(["AAPL"])
    import asyncio

    await asyncio.sleep(0.15)
    await src.stop()
    _, client = fake_massive
    assert client.get_snapshot_all.call_count >= 2
