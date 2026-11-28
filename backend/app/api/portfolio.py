from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from app.services import portfolio, trading

from .schemas import TradeRequest

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("")
async def get_portfolio() -> dict:
    return await asyncio.to_thread(portfolio.get_portfolio)


@router.post("/trade")
async def trade(body: TradeRequest) -> dict:
    return await trading.execute_trade(body.ticker, body.side, body.quantity)


@router.get("/history")
async def history(
    limit: int = Query(portfolio.DEFAULT_HISTORY_LIMIT, ge=1, le=portfolio.MAX_HISTORY_LIMIT),
) -> dict:
    return await asyncio.to_thread(portfolio.get_history, limit)
