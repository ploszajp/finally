"""SSE endpoint streaming prices from the PriceCache.

The stream only ends when the client disconnects, and uvicorn waits for open
connections before running shutdown. Always run the server with
--timeout-graceful-shutdown (see planning/PLAN.md section 11).
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

logger = logging.getLogger(__name__)

KEEPALIVE_SECONDS = 10.0


def create_stream_router(
    price_cache: PriceCache,
    interval: float = 0.5,
    stop_event: threading.Event | None = None,
) -> APIRouter:
    """Build a fresh router (no shared module state) bound to the given cache.

    Setting `stop_event` ends every open stream within one interval, so server shutdown
    does not have to cancel them (uvicorn logs a CancelledError traceback when it does).
    """
    router = APIRouter(prefix="/api/stream", tags=["streaming"])

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _generate_events(price_cache, request, interval, stop_event=stop_event),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router


async def _generate_events(
    price_cache: PriceCache,
    request: Request,
    interval: float = 0.5,
    keepalive_interval: float = KEEPALIVE_SECONDS,
    stop_event: threading.Event | None = None,
) -> AsyncGenerator[str, None]:
    """Yield one aggregate `data:` event per cache change, until disconnect or stop.

    The first event is always a full snapshot, even if empty (`{}`), so that a
    reconnecting client drops tickers that no longer exist. While nothing
    changes, an SSE comment is sent periodically to keep the connection open.
    """
    yield "retry: 1000\n\n"

    last_version = -1
    last_sent = time.monotonic()
    while not (stop_event and stop_event.is_set()) and not await request.is_disconnected():
        # Read the version first: a write in between only causes one extra event.
        version = price_cache.version
        if version != last_version:
            last_version = version
            payload = json.dumps({t: u.to_dict() for t, u in price_cache.get_all().items()})
            last_sent = time.monotonic()
            yield f"data: {payload}\n\n"
        elif time.monotonic() - last_sent >= keepalive_interval:
            last_sent = time.monotonic()
            yield ": keepalive\n\n"
        await asyncio.sleep(interval)
