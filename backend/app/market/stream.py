"""SSE endpoint streaming prices from the PriceCache."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

logger = logging.getLogger(__name__)


def create_stream_router(price_cache: PriceCache, interval: float = 0.5) -> APIRouter:
    """Build a fresh router (no shared module state) bound to the given cache."""
    router = APIRouter(prefix="/api/stream", tags=["streaming"])

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _generate_events(price_cache, request, interval),
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
) -> AsyncGenerator[str, None]:
    """Yield one aggregate `data:` event per cache change, until disconnect."""
    yield "retry: 1000\n\n"

    last_version = -1
    try:
        while True:
            if await request.is_disconnected():
                break
            version = price_cache.version
            if version != last_version:
                last_version = version
                prices = price_cache.get_all()
                if prices:
                    payload = json.dumps({t: u.to_dict() for t, u in prices.items()})
                    yield f"data: {payload}\n\n"
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("SSE stream cancelled")
