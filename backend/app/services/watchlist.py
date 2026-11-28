"""Watchlist management, keeping the market source's tracked tickers in sync (PLAN.md §6)."""

from __future__ import annotations

from app.db import DuplicateTickerError, WatchlistEntry
from app.db import repository as repo
from app.market import PriceCache, normalize_ticker

from .errors import AlreadyOnWatchlistError, NotOnWatchlistError
from .state import get_state


def _item(entry: WatchlistEntry, cache: PriceCache) -> dict:
    update = cache.get(entry.ticker)
    return {
        "ticker": entry.ticker,
        "price": update.price if update else None,
        "previous_price": update.previous_price if update else None,
        "change_percent": update.change_percent if update else None,
        "day_change_percent": update.day_change_percent if update else None,
        "direction": update.direction if update else "flat",
        "added_at": entry.added_at,
    }


def get_watchlist() -> list[dict]:
    state = get_state()
    with state.db.connection() as conn:
        entries = repo.get_watchlist(conn)
    return [_item(e, state.cache) for e in entries]


async def add_to_watchlist(ticker: str) -> dict:
    """Add a ticker and start tracking it. Raises InvalidTickerError / AlreadyOnWatchlistError."""
    state = get_state()
    ticker = normalize_ticker(ticker)
    async with state.ticker_lock:
        try:
            with state.db.connection() as conn:
                entry = repo.add_watchlist(conn, ticker)
        except DuplicateTickerError:
            raise AlreadyOnWatchlistError(ticker) from None
        await state.source.add_ticker(ticker)
    return _item(entry, state.cache)


async def remove_from_watchlist(ticker: str) -> dict:
    """Remove a ticker; stop tracking it unless a position is open.

    Raises InvalidTickerError / NotOnWatchlistError.
    """
    state = get_state()
    ticker = normalize_ticker(ticker)
    async with state.ticker_lock:
        with state.db.connection() as conn:
            if not repo.remove_watchlist(conn, ticker):
                raise NotOnWatchlistError(ticker)
            held = repo.get_position(conn, ticker) is not None
        if not held:
            await state.source.remove_ticker(ticker)
    return {"ticker": ticker, "removed": True}


def tracked_tickers() -> list[str]:
    """Watchlist ∪ open positions: the set the market source must track."""
    with get_state().db.connection() as conn:
        tickers = [e.ticker for e in repo.get_watchlist(conn)]
        tickers += [p.ticker for p in repo.list_positions(conn)]
    return list(dict.fromkeys(tickers))
