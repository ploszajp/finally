"""Market order execution (API.md §3 "Trade execution rules")."""

from __future__ import annotations

import asyncio
import logging
import math

from app.db import repository as repo
from app.market import normalize_ticker

from .errors import TradeError
from .portfolio import build_portfolio, record_snapshot
from .state import AppState, get_state

logger = logging.getLogger(__name__)

SIDES = ("buy", "sell")
QTY_DECIMALS = 4
EPSILON = 1e-9
# Far above anything $10k can buy; keeps totals finite and error messages readable
# for absurd inputs (e.g. from the LLM).
MAX_QUANTITY = 1e9


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _qty(value: float) -> str:
    return f"{value:g}"


def _execute_in_db(state: AppState, ticker: str, side: str, quantity: float, price: float):
    """Validate and apply the trade in one BEGIN IMMEDIATE transaction.

    Returns (trade record, portfolio dict, position_closed).
    """
    total = round(price * quantity, 2)
    with state.db.transaction() as conn:
        cash = repo.get_cash(conn)
        position = repo.get_position(conn, ticker)
        old_qty = position.quantity if position else 0.0
        closed = False

        if side == "buy":
            if total > cash + EPSILON:
                raise TradeError(f"Insufficient cash: need {_money(total)}, have {_money(cash)}")
            new_qty = round(old_qty + quantity, QTY_DECIMALS)
            old_cost = old_qty * position.avg_cost if position else 0.0
            avg_cost = round((old_cost + quantity * price) / new_qty, 4)
            repo.upsert_position(conn, ticker, new_qty, avg_cost)
            repo.set_cash(conn, round(cash - total, 2))
        else:
            if position is None or quantity > old_qty + EPSILON:
                raise TradeError(
                    f"Insufficient shares: trying to sell {_qty(quantity)} {ticker}, "
                    f"have {_qty(old_qty)}"
                )
            remaining = round(old_qty - quantity, QTY_DECIMALS)
            if remaining <= 0:
                repo.delete_position(conn, ticker)
                closed = True
            else:
                repo.upsert_position(conn, ticker, remaining, position.avg_cost)
            repo.set_cash(conn, round(cash + total, 2))

        trade = repo.insert_trade(conn, ticker, side, quantity, price)
        portfolio = build_portfolio(conn, state.cache)
    return trade, total, portfolio, closed


async def execute_trade(ticker: str, side: str, quantity: float) -> dict:
    """Execute a market order at the current cached price.

    Returns {"trade": {...}, "portfolio": {...}} (API.md §3).
    Raises InvalidTickerError for a malformed ticker and TradeError for any rule violation.
    """
    state = get_state()
    ticker = normalize_ticker(ticker)
    side = str(side).strip().lower()
    if side not in SIDES:
        raise TradeError(f"Invalid side: {side!r} (expected 'buy' or 'sell')")
    try:
        quantity = round(float(quantity), QTY_DECIMALS)
    except (TypeError, ValueError):
        raise TradeError("Quantity must be a number") from None
    if not quantity > 0:  # also rejects NaN
        raise TradeError("Quantity must be greater than 0")
    if not math.isfinite(quantity) or quantity > MAX_QUANTITY:
        raise TradeError("Quantity is too large")

    # Held for the whole trade so a concurrent watchlist removal cannot untrack the ticker
    # between reading the price and opening the position.
    async with state.ticker_lock:
        price = state.cache.get_price(ticker)
        if price is None:
            raise TradeError(f"No price available for {ticker}. Add it to the watchlist first.")

        trade, total, portfolio, closed = await asyncio.to_thread(
            _execute_in_db, state, ticker, side, quantity, price
        )

        if closed:
            with state.db.connection() as conn:
                watched = any(e.ticker == ticker for e in repo.get_watchlist(conn))
            if not watched:
                await state.source.remove_ticker(ticker)

    try:
        await asyncio.to_thread(record_snapshot)
    except Exception:  # a failed snapshot must not report a committed trade as failed
        logger.exception("Snapshot after trade failed")

    logger.info("Trade executed: %s %s %s @ %s", side, quantity, ticker, price)
    return {
        "trade": {
            "id": trade.id,
            "ticker": trade.ticker,
            "side": trade.side,
            "quantity": trade.quantity,
            "price": trade.price,
            "total": total,
            "executed_at": trade.executed_at,
        },
        "portfolio": portfolio,
    }
