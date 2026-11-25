"""Tests against the real `massive` SDK; only the HTTP server is stubbed."""

import asyncio
import functools
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import massive
import pytest
from massive.rest.models import TickerSnapshot

from app.market.cache import PriceCache
from app.market.massive_client import MassiveDataSource
from tests.market.helpers import wait_for

TRADE_NS = 1_707_580_800_000_000_000


def wire(ticker, price, ts_ns=TRADE_NS, prev_close=188.0):
    """One ticker in the snapshot endpoint's JSON format."""
    data = {"ticker": ticker, "lastTrade": {"p": price, "t": ts_ns, "s": 100}}
    if prev_close is not None:
        data["prevDay"] = {"c": prev_close}
    return data


def snap(*args, **kwargs):
    """Deserialise with the SDK, so attribute names are the real ones."""
    return TickerSnapshot.from_dict(wire(*args, **kwargs))


def make(tickers=("AAPL", "GOOGL")):
    cache = PriceCache()
    src = MassiveDataSource("key", cache, poll_interval=60.0)
    src._tickers = list(tickers)
    src._client = object()  # truthy; _fetch_snapshots is patched
    return cache, src


def respond_with(monkeypatch, src, *snapshots):
    monkeypatch.setattr(src, "_fetch_snapshots", lambda client, tickers: list(snapshots))


class Stub:
    def __init__(self):
        self.status = 200
        self.tickers = [wire("AAPL", 190.5)]
        self.requests = []
        self.release = threading.Event()
        self.release.set()


@pytest.fixture
def stub(monkeypatch):
    """Local HTTP server that the real RESTClient is pointed at."""
    state = Stub()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state.requests.append((self.path, self.headers["Authorization"]))
            state.release.wait(5)
            body = json.dumps({"status": "OK", "tickers": state.tickers}).encode()
            self.send_response(state.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(massive, "RESTClient", functools.partial(massive.RESTClient, base=url))
    yield state
    state.release.set()
    server.shutdown()
    server.server_close()


async def test_contract_request_and_parsing(stub):
    cache = PriceCache()
    src = MassiveDataSource("secret", cache, poll_interval=60.0)
    await src.start(["aapl", "AAPL", "GOOGL", ""])
    try:
        await wait_for(lambda: "AAPL" in cache)
    finally:
        await src.stop()

    path, auth = stub.requests[0]
    url = urlsplit(path)
    assert url.path == "/v2/snapshot/locale/us/markets/stocks/tickers"
    assert parse_qs(url.query)["tickers"] == ["AAPL,GOOGL"]
    assert auth == "Bearer secret"

    update = cache.get("AAPL")
    assert update.price == 190.5
    assert update.timestamp == 1_707_580_800.0
    assert update.reference_price == 188.0
    assert update.day_change_percent == pytest.approx(1.3298)
    assert src.last_error is None and src.last_success_at is not None


async def test_http_error_is_reported_and_polling_continues(stub):
    stub.status = 401
    cache = PriceCache()
    src = MassiveDataSource("bad", cache, poll_interval=0.01)
    await src.start(["AAPL"])
    try:
        await wait_for(lambda: src.last_error is not None)
        assert len(cache) == 0 and src.last_success_at is None
        stub.status = 200
        await wait_for(lambda: "AAPL" in cache)
        await wait_for(lambda: src.last_error is None)
    finally:
        await src.stop()


async def test_start_does_not_wait_for_first_poll(stub):
    stub.release.clear()  # the server holds the response
    cache = PriceCache()
    src = MassiveDataSource("key", cache, poll_interval=60.0)
    started = time.monotonic()
    await src.start(["AAPL"])
    assert time.monotonic() - started < 1.0
    assert len(cache) == 0
    stub.release.set()
    await wait_for(lambda: "AAPL" in cache)
    await src.stop()


async def test_start_twice_raises_and_stop_is_idempotent(stub):
    src = MassiveDataSource("key", PriceCache(), poll_interval=60.0)
    await src.start(["AAPL"])
    with pytest.raises(RuntimeError):
        await src.start(["AAPL"])
    await src.stop()
    await src.stop()
    assert src._task is None and src._client is None


async def test_removed_during_in_flight_poll_stays_removed(stub):
    stub.tickers = [wire("AAPL", 190.5), wire("TSLA", 250.0)]
    stub.release.clear()
    cache = PriceCache()
    src = MassiveDataSource("key", cache, poll_interval=60.0)
    await src.start(["AAPL", "TSLA"])
    await wait_for(lambda: stub.requests)
    await src.remove_ticker("TSLA")
    stub.release.set()
    await wait_for(lambda: "AAPL" in cache)
    await asyncio.sleep(0.02)
    assert set(cache.get_all()) == {"AAPL"}
    await src.stop()


async def test_missing_timestamp_falls_back_to_now(monkeypatch):
    cache, src = make()
    respond_with(monkeypatch, src, snap("AAPL", 1.0, ts_ns=None))
    before = time.time()
    await src._poll_once()
    assert before <= cache.get("AAPL").timestamp <= time.time()


async def test_missing_previous_day_uses_first_price(monkeypatch):
    cache, src = make()
    respond_with(monkeypatch, src, snap("AAPL", 100.0, prev_close=None))
    await src._poll_once()
    respond_with(monkeypatch, src, snap("AAPL", 110.0, prev_close=None))
    await src._poll_once()
    assert cache.get("AAPL").reference_price == 100.0
    assert cache.get("AAPL").day_change_percent == 10.0


@pytest.mark.parametrize(
    "bad",
    [
        TickerSnapshot.from_dict({"ticker": "BAD"}),  # no lastTrade
        snap("BAD", None),
        snap("BAD", 0),
    ],
)
async def test_unusable_snapshot_skipped(monkeypatch, bad):
    cache, src = make(["AAPL", "BAD"])
    respond_with(monkeypatch, src, bad, snap("AAPL", 190.5))
    await src._poll_once()
    assert set(cache.get_all()) == {"AAPL"}


async def test_no_usable_snapshots_sets_last_error(monkeypatch):
    _, src = make()
    respond_with(monkeypatch, src)
    await src._poll_once()
    assert src.last_error is not None


async def test_error_keeps_last_prices(monkeypatch):
    cache, src = make()
    cache.update("AAPL", 100.0)

    def boom(client, tickers):
        raise RuntimeError("429")

    monkeypatch.setattr(src, "_fetch_snapshots", boom)
    await src._poll_once()
    assert cache.get_price("AAPL") == 100.0
    assert src.last_error == "429"


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
