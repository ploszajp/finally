from __future__ import annotations

import asyncio

from fastapi import APIRouter

from app.services import watchlist

from .schemas import WatchlistAddRequest

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("")
async def get_watchlist() -> dict:
    return {"watchlist": await asyncio.to_thread(watchlist.get_watchlist)}


@router.post("", status_code=201)
async def add(body: WatchlistAddRequest) -> dict:
    return await watchlist.add_to_watchlist(body.ticker)


@router.delete("/{ticker}")
async def remove(ticker: str) -> dict:
    return await watchlist.remove_from_watchlist(ticker)
