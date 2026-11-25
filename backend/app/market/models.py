"""Shared data model for market data."""
from __future__ import annotations

import re
from dataclasses import dataclass

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def normalize_ticker(ticker: str) -> str:
    """Trim + upper-case a ticker and validate its format. Raises ValueError."""
    t = (ticker or "").strip().upper()
    if not _TICKER_RE.match(t):
        raise ValueError(f"Invalid ticker: {ticker!r}")
    return t


@dataclass(frozen=True, slots=True)
class PriceUpdate:
    """Latest price of a ticker.

    ``timestamp`` is epoch seconds (float). ``open_price`` is the reference
    for the "daily change": the previous close for Massive, or the first
    price seen by the server in this session for the simulator.
    """

    ticker: str
    price: float
    previous_price: float
    timestamp: float
    open_price: float

    @property
    def direction(self) -> str:
        if self.price > self.previous_price:
            return "up"
        if self.price < self.previous_price:
            return "down"
        return "flat"

    @property
    def change(self) -> float:
        return self.price - self.open_price

    @property
    def change_pct(self) -> float:
        return 0.0 if self.open_price == 0 else (self.price / self.open_price - 1) * 100

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "price": round(self.price, 4),
            "previous_price": round(self.previous_price, 4),
            "timestamp": self.timestamp,
            "direction": self.direction,
            "open_price": round(self.open_price, 4),
            "change_pct": round(self.change_pct, 4),
        }
