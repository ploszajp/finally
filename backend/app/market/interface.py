"""Abstract market data source interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class MarketDataSource(ABC):
    """Contract for market data providers.

    Implementations push updates into a shared PriceCache on their own schedule.

    Callers own the set of tracked tickers. It must be the union of the watchlist
    and all open positions: pass that union to start(), and do not call
    remove_ticker() while a position is open, because removal also drops the
    cached price needed for valuation and trading.

    Methods that take a single ticker raise InvalidTickerError for bad input.
    """

    # Feed health, for logs and a future /api/health. The simulator leaves both unset.
    last_success_at: float | None = None  # Unix seconds of the last usable poll
    last_error: str | None = None  # None once a poll succeeds

    @abstractmethod
    async def start(self, tickers: list[str]) -> None:
        """Begin producing price updates. Invalid tickers are logged and skipped.

        Raises RuntimeError if the source is already running.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Stop background work. Safe to call multiple times."""

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Add a ticker to the active set. No-op if already present."""

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker (and its cached price). No-op if not present."""

    @abstractmethod
    def get_tickers(self) -> list[str]:
        """Return the currently tracked tickers."""
