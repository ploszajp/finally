"""Thread-safe in-memory price cache."""

from __future__ import annotations

import math
import time
from threading import Lock

from .models import PriceUpdate


def _valid_price(value: float) -> bool:
    # Checked after rounding, so a value that rounds to 0.00 is rejected too.
    return math.isfinite(value) and round(value, 2) > 0


class PriceCache:
    """Latest price per ticker. Written by a data source, read by SSE/portfolio."""

    def __init__(self) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._lock = Lock()
        self._version = 0

    def update(
        self,
        ticker: str,
        price: float,
        timestamp: float | None = None,
        reference_price: float | None = None,
    ) -> PriceUpdate:
        """Store a new price.

        Raises ValueError unless the price is finite and positive. A missing or
        non-finite timestamp becomes the current time. If reference_price is not
        given (or invalid), the ticker keeps its existing one; a new ticker uses
        its first price.
        """
        if not _valid_price(price):
            raise ValueError(f"Invalid price for {ticker}: {price!r}")
        with self._lock:
            ts = timestamp if timestamp is not None and math.isfinite(timestamp) else time.time()
            prev = self._prices.get(ticker)
            previous_price = prev.price if prev else price
            if reference_price is None or not _valid_price(reference_price):
                reference_price = prev.reference_price if prev else price
            update = PriceUpdate(
                ticker=ticker,
                price=round(price, 2),
                previous_price=round(previous_price, 2),
                timestamp=ts,
                reference_price=round(reference_price, 2),
            )
            self._prices[ticker] = update
            self._version += 1
            return update

    def get(self, ticker: str) -> PriceUpdate | None:
        with self._lock:
            return self._prices.get(ticker)

    def get_all(self) -> dict[str, PriceUpdate]:
        with self._lock:
            return dict(self._prices)

    def get_price(self, ticker: str) -> float | None:
        update = self.get(ticker)
        return update.price if update else None

    def remove(self, ticker: str) -> None:
        with self._lock:
            if self._prices.pop(ticker, None) is not None:
                self._version += 1

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def __len__(self) -> int:
        with self._lock:
            return len(self._prices)

    def __contains__(self, ticker: str) -> bool:
        with self._lock:
            return ticker in self._prices
