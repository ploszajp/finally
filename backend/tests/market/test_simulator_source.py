import asyncio

from app.market.cache import PriceCache
from app.market.simulator import SimulatorDataSource


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
    await asyncio.sleep(0.15)
    assert cache.version > v
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
    await asyncio.sleep(0.1)
    assert calls["n"] > 1
    await src.stop()
