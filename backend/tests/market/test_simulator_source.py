import asyncio

import pytest

from app.market.cache import PriceCache
from app.market.simulator import SimulatorDataSource
from tests.market.helpers import wait_for


async def test_start_seeds_cache():
    cache = PriceCache()
    src = SimulatorDataSource(cache, update_interval=0.05)
    await src.start(["AAPL", "GOOGL"])
    assert cache.get("AAPL") is not None and cache.get("GOOGL") is not None
    await src.stop()


async def test_prices_update():
    cache = PriceCache()
    src = SimulatorDataSource(cache, update_interval=0.01)
    await src.start(["AAPL"])
    v = cache.version
    await wait_for(lambda: cache.version > v)
    await src.stop()


async def test_stop_halts_updates_and_is_idempotent():
    cache = PriceCache()
    src = SimulatorDataSource(cache, update_interval=0.01)
    await src.start(["AAPL"])
    await src.stop()
    await src.stop()
    v = cache.version
    await asyncio.sleep(0.05)
    assert cache.version == v


async def test_add_remove_ticker_normalizes():
    cache = PriceCache()
    src = SimulatorDataSource(cache, update_interval=0.05)
    await src.start(["AAPL"])
    await src.add_ticker(" tsla ")
    assert "TSLA" in src.get_tickers()
    assert cache.get("TSLA") is not None
    await src.remove_ticker("tsla")
    assert "TSLA" not in src.get_tickers()
    assert cache.get("TSLA") is None
    await src.stop()


async def test_empty_start_then_add():
    cache = PriceCache()
    src = SimulatorDataSource(cache, update_interval=0.05)
    await src.start([])
    assert src.get_tickers() == []
    await src.add_ticker("NVDA")
    assert cache.get("NVDA") is not None
    await src.stop()


async def test_add_before_start_is_noop():
    src = SimulatorDataSource(PriceCache())
    await src.add_ticker("AAPL")
    assert src.get_tickers() == []


async def test_loop_survives_step_exception():
    cache = PriceCache()
    src = SimulatorDataSource(cache, update_interval=0.01)
    await src.start(["AAPL"])
    calls = {"n": 0}
    real = src._sim.step

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return real()

    src._sim.step = flaky
    await wait_for(lambda: calls["n"] > 1)
    await src.stop()


async def test_start_twice_raises():
    src = SimulatorDataSource(PriceCache())
    await src.start(["AAPL"])
    task = src._task
    with pytest.raises(RuntimeError):
        await src.start(["MSFT"])
    assert src._task is task and src.get_tickers() == ["AAPL"]
    await src.stop()


async def test_start_skips_invalid_tickers():
    cache = PriceCache()
    src = SimulatorDataSource(cache)
    await src.start(["aapl", "", "AAPL", "bad ticker"])
    assert src.get_tickers() == ["AAPL"] and set(cache.get_all()) == {"AAPL"}
    await src.stop()


async def test_reference_price_is_session_start():
    cache = PriceCache()
    src = SimulatorDataSource(cache, update_interval=0.001)
    await src.start(["AAPL"])
    v = cache.version
    await wait_for(lambda: cache.version > v + 5)
    assert cache.get("AAPL").reference_price == 190.0
    await src.stop()
