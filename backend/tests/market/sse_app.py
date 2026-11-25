"""Minimal app for the real-server SSE test."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.market import PriceCache, create_stream_router
from app.market.simulator import SimulatorDataSource

cache = PriceCache()
source = SimulatorDataSource(cache, update_interval=0.05)


@asynccontextmanager
async def lifespan(app):
    await source.start(["AAPL"])
    yield
    await source.stop()
    print("LIFESPAN-SHUTDOWN-COMPLETE", flush=True)


app = FastAPI(lifespan=lifespan)
app.include_router(create_stream_router(cache, interval=0.05))
