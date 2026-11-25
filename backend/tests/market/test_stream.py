import json

from app.market import PriceCache, create_stream_router
from app.market.stream import _generate_events


class FakeRequest:
    def __init__(self, disconnect_after=2):
        self.n = 0
        self.after = disconnect_after

    async def is_disconnected(self):
        self.n += 1
        return self.n > self.after


async def collect(cache, req):
    return [e async for e in _generate_events(cache, req, interval=0.001)]


async def test_events_retry_then_data():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    events = await collect(cache, FakeRequest(2))
    assert events[0] == "retry: 1000\n\n"
    assert len(events) == 2  # unchanged cache => only one data event
    body = json.loads(events[1][len("data: ") :])
    assert body["AAPL"]["price"] == 190.0
    assert events[1].endswith("\n\n")


async def test_empty_cache_sends_empty_snapshot_once():
    events = await collect(PriceCache(), FakeRequest(3))
    assert events == ["retry: 1000\n\n", "data: {}\n\n"]


async def test_removing_last_ticker_sends_empty_snapshot():
    cache = PriceCache()
    cache.update("AAPL", 1.0)
    events = []
    async for event in _generate_events(cache, FakeRequest(4), interval=0.001):
        events.append(event)
        if len(events) == 2:
            cache.remove("AAPL")
    assert events[-1] == "data: {}\n\n"
    assert len(events) == 3


async def test_keepalive_while_unchanged():
    events = [
        e
        async for e in _generate_events(
            PriceCache(), FakeRequest(4), interval=0.01, keepalive_interval=0.001
        )
    ]
    assert events[2:] == [": keepalive\n\n"] * 3


async def test_immediate_disconnect():
    cache = PriceCache()
    cache.update("A", 1.0)
    events = await collect(cache, FakeRequest(0))
    assert events == ["retry: 1000\n\n"]


def test_router_registered_once_per_call():
    a = create_stream_router(PriceCache())
    b = create_stream_router(PriceCache())
    assert a is not b
    assert [r.path for r in a.routes] == ["/api/stream/prices"]
    assert [r.path for r in b.routes] == ["/api/stream/prices"]


async def test_http_endpoint_headers_and_first_event():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    # Call the endpoint function directly to inspect the response without an infinite stream.
    router = create_stream_router(cache, interval=0.01)
    endpoint = router.routes[0].endpoint
    resp = await endpoint(FakeRequest(1))
    assert resp.media_type == "text/event-stream"
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers["x-accel-buffering"] == "no"
    first = [c async for c in resp.body_iterator][:2]
    assert first[0] == "retry: 1000\n\n"
    assert first[1].startswith("data: ")
