import asyncio
import math

import httpx
import pytest

from app.market import (
    MarketDataSource, MassiveClient, PriceCache, Simulator,
    create_market_source, normalize_ticker, parse_snapshot,
)
from app.market.simulator import SEED_PRICES, seed_price

# ---------- models / cache ----------

def test_normalize_ticker():
    assert normalize_ticker("  aapl ") == "AAPL"
    assert normalize_ticker("BRK.B") == "BRK.B"
    for bad in ["", "  ", "1AB", "A B", "TOOLONGTICKER1", "A$"]:
        with pytest.raises(ValueError):
            normalize_ticker(bad)


def test_cache_first_update_and_direction():
    c = PriceCache()
    u = c.update("AAPL", 100.0, 1.0)
    assert u.previous_price == 100.0 and u.direction == "flat" and u.open_price == 100.0
    u = c.update("AAPL", 101.0, 2.0)
    assert u.previous_price == 100.0 and u.direction == "up"
    assert u.change_pct == pytest.approx(1.0)
    u = c.update("AAPL", 99.0, 3.0)
    assert u.direction == "down" and u.open_price == 100.0
    assert c.get_price("AAPL") == 99.0
    assert u.to_dict()["direction"] == "down"


def test_cache_open_price_override_and_remove():
    c = PriceCache()
    c.update("X", 10, open_price=8)
    assert c.get("X").open_price == 8
    assert "X" in c and len(c) == 1
    c.remove("X")
    assert c.get("X") is None and c.get_all() == {}
    c.remove("X")  # idempotent


def test_cache_rejects_bad_price():
    with pytest.raises(ValueError):
        PriceCache().update("X", 0)


# ---------- interface ----------

def test_abstract_interface():
    with pytest.raises(TypeError):
        MarketDataSource(PriceCache())
    assert issubclass(Simulator, MarketDataSource)
    assert issubclass(MassiveClient, MarketDataSource)


async def test_set_tickers_diff():
    c = PriceCache()
    sim = Simulator(c, seed=1)
    await sim.set_tickers(["aapl", "msft"])
    assert sim.tickers == {"AAPL", "MSFT"}
    await sim.set_tickers(["MSFT", "tsla"])
    assert sim.tickers == {"MSFT", "TSLA"}
    assert "AAPL" not in c and "TSLA" in c


# ---------- simulator ----------

def test_seed_price_known_and_unknown():
    assert seed_price("AAPL") == SEED_PRICES["AAPL"]
    p = seed_price("ZZZZ")
    assert 20 <= p <= 500 and p == seed_price("ZZZZ")


async def test_price_available_right_after_add():
    c = PriceCache()
    sim = Simulator(c, seed=1)
    await sim.add_ticker("aapl")
    assert c.get_price("AAPL") == 190.0


async def test_step_stays_positive_and_changes():
    c = PriceCache()
    sim = Simulator(c, seed=42, event_prob=0.05, sim_speed=1000)
    await sim.set_tickers(SEED_PRICES)
    for _ in range(500):
        sim.step()
    for t, u in c.get_all().items():
        assert u.price > 0 and math.isfinite(u.price)
    assert any(c.get(t).price != SEED_PRICES[t] for t in SEED_PRICES)


async def test_events_cause_large_moves():
    c = PriceCache()
    sim = Simulator(c, seed=3, event_prob=1.0)  # every tick is an event
    await sim.add_ticker("AAPL")
    sim.step()
    u = c.get("AAPL")
    assert 0.0199 <= abs(u.price / u.previous_price - 1) <= 0.0501


async def test_gbm_log_return_statistics():
    c = PriceCache()
    sim = Simulator(c, seed=7, event_prob=0.0, sim_speed=5000)
    await sim.add_ticker("V")  # sigma 0.20
    rets, last = [], c.get_price("V")
    for _ in range(4000):
        sim.step()
        p = c.get_price("V")
        rets.append(math.log(p / last))
        last = p
    mean = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
    expected = 0.20 * math.sqrt(sim._dt)
    assert sd == pytest.approx(expected, rel=0.1)


async def test_sector_correlation():
    c = PriceCache()
    sim = Simulator(c, seed=11, event_prob=0.0, sim_speed=5000)
    await sim.set_tickers(["AAPL", "MSFT", "JPM"])
    series = {t: [] for t in sim.tickers}
    last = {t: c.get_price(t) for t in sim.tickers}
    for _ in range(3000):
        sim.step()
        for t in series:
            p = c.get_price(t)
            series[t].append(math.log(p / last[t]))
            last[t] = p

    def corr(a, b):
        ma, mb = sum(a) / len(a), sum(b) / len(b)
        cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        return cov / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))

    assert corr(series["AAPL"], series["MSFT"]) > corr(series["AAPL"], series["JPM"])
    assert corr(series["AAPL"], series["MSFT"]) > 0.3


async def test_simulator_background_task():
    c = PriceCache()
    sim = Simulator(c, interval=0.01, seed=5, sim_speed=1000)
    await sim.start(["AAPL"])
    await sim.start()  # idempotent
    await asyncio.sleep(0.15)
    assert c.get("AAPL").timestamp > 0
    assert c.get("AAPL").price != 190.0
    await sim.stop()
    await sim.stop()
    snapshot = c.get_price("AAPL")
    await asyncio.sleep(0.05)
    assert c.get_price("AAPL") == snapshot


async def test_remove_ticker_clears_state():
    c = PriceCache()
    sim = Simulator(c, seed=1)
    await sim.add_ticker("AAPL")
    await sim.remove_ticker(" aapl")
    assert "AAPL" not in c and "AAPL" not in sim._prices
    sim.step()  # no error with no tickers


# ---------- massive ----------

SNAPSHOT = {
    "status": "OK",
    "tickers": [
        {"ticker": "AAPL", "lastTrade": {"p": 191.5}, "day": {"c": 190.0},
         "prevDay": {"c": 189.0}, "updated": 1_700_000_000_000_000_000},
        {"ticker": "MSFT", "lastTrade": {"p": 0}, "day": {"c": 420.0}, "prevDay": {"c": 418.0}},
        {"ticker": "TSLA", "prevDay": {"c": 250.0}},
        {"ticker": "BAD", "day": {}, "prevDay": {}},
        {"nope": 1},
    ],
}


def test_parse_snapshot():
    r = parse_snapshot(SNAPSHOT)
    assert set(r) == {"AAPL", "MSFT", "TSLA"}
    assert r["AAPL"] == {"price": 191.5, "open_price": 189.0, "timestamp": 1_700_000_000.0}
    assert r["MSFT"]["price"] == 420.0 and r["MSFT"]["timestamp"] is None
    assert r["TSLA"]["price"] == 250.0
    assert parse_snapshot({}) == {}
    assert parse_snapshot({"tickers": None}) == {}


def make_client(handler, **kw):
    c = PriceCache()
    http = httpx.AsyncClient(base_url="https://x.test", transport=httpx.MockTransport(handler))
    return c, MassiveClient(c, "KEY", client=http, **kw)


async def test_poll_once_updates_cache_and_sends_params():
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json=SNAPSHOT)

    c, m = make_client(handler)
    assert await m.poll_once() == 0 and not seen  # nothing tracked
    await m.add_ticker("msft")
    await m.add_ticker("aapl")
    assert await m.poll_once() == 2
    q = seen[0].url.params
    assert q["tickers"] == "AAPL,MSFT" and q["apiKey"] == "KEY"
    assert c.get("AAPL").open_price == 189.0
    assert c.get_price("MSFT") == 420.0
    assert "TSLA" not in c  # untracked ignored


async def test_poll_http_error_raises_and_background_survives():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429)
        return httpx.Response(200, json=SNAPSHOT)

    c, m = make_client(handler, poll_interval=0.01)
    await m.add_ticker("AAPL")
    with pytest.raises(httpx.HTTPStatusError):
        await m.poll_once()
    await m.start()
    await asyncio.sleep(0.1)
    await m.stop()
    assert c.get_price("AAPL") == 191.5


async def test_add_ticker_while_running_polls_immediately():
    c, m = make_client(lambda r: httpx.Response(200, json=SNAPSHOT), poll_interval=3600)
    await m.start()
    await asyncio.sleep(0.02)
    await m.add_ticker("AAPL")
    assert c.get_price("AAPL") == 191.5
    await m.stop()


# ---------- factory ----------

def test_factory_selection():
    assert isinstance(create_market_source(PriceCache(), {}), Simulator)
    assert isinstance(create_market_source(PriceCache(), {"MASSIVE_API_KEY": "  "}), Simulator)
    assert isinstance(create_market_source(PriceCache(), {"MASSIVE_API_KEY": "k"}), MassiveClient)
