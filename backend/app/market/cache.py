"""Thread-safe in-memory price cache shared by data sources and SSE."""
from __future__ import annotations

import threading
import time

from .models import PriceUpdate


class PriceCache:
    def __init__(self) -> None:
        self._data: dict[str, PriceUpdate] = {}
        self._lock = threading.Lock()

    def update(
        self,
        ticker: str,
        price: float,
        timestamp: float | None = None,
        open_price: float | None = None,
    ) -> PriceUpdate:
        """Store a new price. First update sets previous_price == price."""
        if price <= 0:
            raise ValueError("price must be positive")
        ts = time.time() if timestamp is None else timestamp
        with self._lock:
            old = self._data.get(ticker)
            if old is None:
                upd = PriceUpdate(ticker, price, price, ts, open_price or price)
            else:
                upd = PriceUpdate(
                    ticker, price, old.price, ts, open_price or old.open_price
                )
            self._data[ticker] = upd
            return upd

    def get(self, ticker: str) -> PriceUpdate | None:
        with self._lock:
            return self._data.get(ticker)

    def get_price(self, ticker: str) -> float | None:
        upd = self.get(ticker)
        return upd.price if upd else None

    def get_all(self) -> dict[str, PriceUpdate]:
        with self._lock:
            return dict(self._data)

    def remove(self, ticker: str) -> None:
        with self._lock:
            self._data.pop(ticker, None)

    def __contains__(self, ticker: str) -> bool:
        with self._lock:
            return ticker in self._data

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
