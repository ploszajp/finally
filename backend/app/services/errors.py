"""Domain errors. Their str() is a user-facing sentence; the API maps them to status codes."""

from __future__ import annotations


class TradeError(ValueError):
    """A trade failed validation (quantity, price availability, cash, shares). HTTP 400."""


class WatchlistError(Exception):
    """Base class for watchlist rule violations."""


class AlreadyOnWatchlistError(WatchlistError):
    """HTTP 409."""

    def __init__(self, ticker: str) -> None:
        super().__init__(f"{ticker} is already on the watchlist")
        self.ticker = ticker


class NotOnWatchlistError(WatchlistError):
    """HTTP 404."""

    def __init__(self, ticker: str) -> None:
        super().__init__(f"{ticker} is not on the watchlist")
        self.ticker = ticker
