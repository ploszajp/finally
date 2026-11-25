"""Unified market data interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from .cache import PriceCache
from .models import normalize_ticker


class MarketDataSource(ABC):
    """A background producer that keeps a PriceCache up to date.

    The set of tracked tickers is pushed in by the app (watchlist union open
    positions) via add_ticker/remove_ticker/set_tickers.
    """

    def __init__(self, cache: PriceCache) -> None:
        self.cache = cache
        self._tickers: set[str] = set()

    @property
    def tickers(self) -> frozenset[str]:
        return frozenset(self._tickers)

    @abstractmethod
    async def start(self, tickers: Iterable[str] = ()) -> None:
        """Start the background task tracking the given tickers."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the background task (idempotent)."""

    async def add_ticker(self, ticker: str) -> str:
        """Track a ticker; returns the normalized symbol."""
        t = normalize_ticker(ticker)
        if t not in self._tickers:
            self._tickers.add(t)
            await self._on_added(t)
        return t

    async def remove_ticker(self, ticker: str) -> None:
        t = normalize_ticker(ticker)
        if t in self._tickers:
            self._tickers.discard(t)
            self.cache.remove(t)

    async def set_tickers(self, tickers: Iterable[str]) -> None:
        wanted = {normalize_ticker(t) for t in tickers}
        for t in self._tickers - wanted:
            await self.remove_ticker(t)
        for t in wanted - self._tickers:
            await self.add_ticker(t)

    async def _on_added(self, ticker: str) -> None:
        """Hook: called after a new ticker is tracked."""
