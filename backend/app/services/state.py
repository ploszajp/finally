"""Process-wide application state: database handle, price cache and market data source."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.db import Database
from app.market import MarketDataSource, PriceCache


@dataclass
class AppState:
    db: Database
    cache: PriceCache
    source: MarketDataSource
    # Serialises "change tracked tickers" decisions (watchlist/position checks + add/remove).
    ticker_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_state: AppState | None = None


def set_state(state: AppState | None) -> None:
    global _state
    _state = state


def get_state() -> AppState:
    if _state is None:
        raise RuntimeError("Application state is not initialised (lifespan not started)")
    return _state
