# Market Data Backend — Detailed Design

Implementation-ready design for the FinAlly market data subsystem. Covers the unified interface, in-memory price cache, GBM simulator, Massive API client, SSE streaming endpoint, and FastAPI lifecycle integration.

Everything in this document lives under `backend/app/market/`.

---

## Table of Contents

1. [File Structure](#1-file-structure)
2. [Data Model — `models.py`](#2-data-model)
3. [Price Cache — `cache.py`](#3-price-cache)
4. [Abstract Interface — `interface.py`](#4-abstract-interface)
5. [Seed Prices & Ticker Parameters — `seed_prices.py`](#5-seed-prices--ticker-parameters)
6. [GBM Simulator — `simulator.py`](#6-gbm-simulator)
7. [Massive API Client — `massive_client.py`](#7-massive-api-client)
8. [Factory — `factory.py`](#8-factory)
9. [SSE Streaming Endpoint — `stream.py`](#9-sse-streaming-endpoint)
10. [FastAPI Lifecycle Integration](#10-fastapi-lifecycle-integration)
11. [Watchlist Coordination](#11-watchlist-coordination)
12. [Testing Strategy](#12-testing-strategy)
13. [Error Handling & Edge Cases](#13-error-handling--edge-cases)
14. [Configuration Summary](#14-configuration-summary)

---

## 1. File Structure

```
backend/
  app/
    market/
      __init__.py             # Re-exports: PriceUpdate, PriceCache, MarketDataSource, create_market_data_source
      models.py               # PriceUpdate dataclass
      cache.py                # PriceCache (thread-safe in-memory store)
      interface.py            # MarketDataSource ABC
      seed_prices.py          # SEED_PRICES, TICKER_PARAMS, DEFAULT_PARAMS, CORRELATION_GROUPS
      simulator.py            # GBMSimulator + SimulatorDataSource
      massive_client.py       # MassiveDataSource
      factory.py              # create_market_data_source()
      tickers.py              # normalize_ticker(), InvalidTickerError
      stream.py               # SSE endpoint (FastAPI router)
```

Each file has a single responsibility. The `__init__.py` re-exports the public API so that the rest of the backend imports from `app.market` without reaching into submodules.

---

## 2. Data Model

**File: `backend/app/market/models.py`**

`PriceUpdate` is the only data structure that leaves the market data layer. Every downstream consumer — SSE streaming, portfolio valuation, trade execution — works exclusively with this type.

```python
"""Data model for market data."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PriceUpdate:
    """Immutable snapshot of a single ticker's price at a point in time."""

    ticker: str
    price: float
    previous_price: float
    timestamp: float = field(default_factory=time.time)  # Unix seconds
    # Baseline for the daily change. Simulator: first price of the session.
    # Massive: previous day's close. 0.0 means unknown.
    reference_price: float = 0.0

    @property
    def change(self) -> float:
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
        if self.previous_price == 0:
            return 0.0
        return round((self.price - self.previous_price) / self.previous_price * 100, 4)

    @property
    def day_change_percent(self) -> float:
        """Percentage change against reference_price (the "daily change %")."""
        if self.reference_price <= 0:
            return 0.0
        return round((self.price - self.reference_price) / self.reference_price * 100, 4)

    @property
    def direction(self) -> str:
        if self.price > self.previous_price:
            return "up"
        if self.price < self.previous_price:
            return "down"
        return "flat"

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "price": self.price,
            "previous_price": self.previous_price,
            "timestamp": self.timestamp,
            "change": self.change,
            "change_percent": self.change_percent,
            "direction": self.direction,
            "reference_price": self.reference_price,
            "day_change_percent": self.day_change_percent,
        }
```

### Design decisions

- **`frozen=True`**: Price updates are immutable value objects. Once created they never change, which makes them safe to share across async tasks without copying.
- **`slots=True`**: Minor memory optimization — we create many of these per second.
- **Computed properties** (`change`, `direction`, `change_percent`): Derived from `price` and `previous_price` so they can never be inconsistent. No risk of a stale `direction` field.
- **`to_dict()`**: Single serialization point used by both the SSE endpoint and REST API responses.

---

## 3. Price Cache

**File: `backend/app/market/cache.py`**

The price cache is the central data hub. Data sources write to it; SSE streaming and portfolio valuation read from it. It must be thread-safe because the simulator/poller may run in a thread pool executor while SSE reads happen on the async event loop.

```python
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
```

### Why a version counter?

The SSE streaming loop polls the cache every ~500ms. Without a version counter, it would serialize and send all prices every tick even if nothing changed (e.g., Massive API only updates every 15s). The version counter lets the SSE loop skip sends when nothing is new:

```python
last_version = -1
while True:
    if price_cache.version != last_version:
        last_version = price_cache.version
        yield format_sse(price_cache.get_all())
    await asyncio.sleep(0.5)
```

### Thread safety rationale

The `threading.Lock` is used instead of `asyncio.Lock` because:
- The Massive client's synchronous `get_snapshot_all()` runs in `asyncio.to_thread()`, which operates in a real OS thread — `asyncio.Lock` would not protect against that.
- The GBM simulator's `step()` is CPU-bound and could also be offloaded to a thread for fairness.
- `threading.Lock` works correctly from both sync threads and the async event loop.

---

## 4. Abstract Interface

**File: `backend/app/market/interface.py`**

```python
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
```

### Why the source writes to the cache instead of returning prices

This push model decouples timing. The simulator ticks at 500ms, Massive polls at 15s, but SSE always reads from the cache at its own 500ms cadence. There is no need for the SSE layer to know which data source is active or what its update interval is.

---

## 5. Seed Prices & Ticker Parameters

**File: `backend/app/market/seed_prices.py`**

Constants only — no logic, no imports beyond stdlib. This file is shared by both the simulator (for initial prices and GBM parameters) and potentially by the Massive client (as fallback prices if the API hasn't responded yet).

```python
"""Seed prices and per-ticker parameters for the market simulator."""

# Realistic starting prices for the default watchlist (as of project creation)
SEED_PRICES: dict[str, float] = {
    "AAPL": 190.00,
    "GOOGL": 175.00,
    "MSFT": 420.00,
    "AMZN": 185.00,
    "TSLA": 250.00,
    "NVDA": 800.00,
    "META": 500.00,
    "JPM": 195.00,
    "V": 280.00,
    "NFLX": 600.00,
}

# Per-ticker GBM parameters
# sigma: annualized volatility (higher = more price movement)
# mu: annualized drift / expected return
TICKER_PARAMS: dict[str, dict[str, float]] = {
    "AAPL":  {"sigma": 0.22, "mu": 0.05},
    "GOOGL": {"sigma": 0.25, "mu": 0.05},
    "MSFT":  {"sigma": 0.20, "mu": 0.05},
    "AMZN":  {"sigma": 0.28, "mu": 0.05},
    "TSLA":  {"sigma": 0.50, "mu": 0.03},   # High volatility
    "NVDA":  {"sigma": 0.40, "mu": 0.08},   # High volatility, strong drift
    "META":  {"sigma": 0.30, "mu": 0.05},
    "JPM":   {"sigma": 0.18, "mu": 0.04},   # Low volatility (bank)
    "V":     {"sigma": 0.17, "mu": 0.04},   # Low volatility (payments)
    "NFLX":  {"sigma": 0.35, "mu": 0.05},
}

# Default parameters for tickers not in the list above (dynamically added)
DEFAULT_PARAMS: dict[str, float] = {"sigma": 0.25, "mu": 0.05}

# Correlation groups for the simulator's Cholesky decomposition
# Tickers in the same group have higher intra-group correlation
CORRELATION_GROUPS: dict[str, set[str]] = {
    "tech": {"AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "NFLX"},
    "finance": {"JPM", "V"},
}

# Correlation coefficients
INTRA_TECH_CORR = 0.6       # Tech stocks move together
INTRA_FINANCE_CORR = 0.5    # Finance stocks move together
CROSS_GROUP_CORR = 0.3      # Between sectors
TSLA_CORR = 0.3             # TSLA does its own thing
DEFAULT_CORR = 0.3           # Unknown tickers
```

---

### Ticker validation — `tickers.py`

```python
"""Ticker normalisation and validation, shared by every code path that accepts a ticker."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

logger = logging.getLogger(__name__)

# 1-10 characters, starting with a letter; "." and "-" cover share classes (BRK.B).
TICKER_PATTERN = re.compile(r"[A-Z][A-Z.\-]{0,9}")


class InvalidTickerError(ValueError):
    """Raised for input that is not a well-formed ticker. API routes map this to 400."""


def normalize_ticker(ticker: str) -> str:
    """Trim and upper-case a ticker, raising InvalidTickerError if the format is wrong.

    This checks the format only, not whether the symbol exists on an exchange.
    """
    normalized = ticker.strip().upper()
    if not TICKER_PATTERN.fullmatch(normalized):
        raise InvalidTickerError(f"Invalid ticker: {ticker!r}")
    return normalized


def normalize_tickers(tickers: Iterable[str]) -> list[str]:
    """Normalise a startup list: drop duplicates, and log and skip invalid entries.

    Used by start(), where one bad stored value must not stop the application.
    """
    result: dict[str, None] = {}
    for ticker in tickers:
        try:
            result[normalize_ticker(ticker)] = None
        except InvalidTickerError as e:
            logger.warning("Skipping ticker: %s", e)
    return list(result)
```

---

## 6. GBM Simulator

**File: `backend/app/market/simulator.py`**

The file contains:
- `seed_price()`: the listed seed price, or a stable hash-derived value in $50–$300 for other tickers.
- `GBMSimulator`: pure math engine. Stateful; holds current prices and advances them one step at a time.
- `SimulatorDataSource`: the `MarketDataSource` implementation that runs the engine in an async loop and writes to the `PriceCache`.

```python
"""GBM market simulator and its MarketDataSource wrapper."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import random

import numpy as np

from .cache import PriceCache
from .interface import MarketDataSource
from .seed_prices import (
    CORRELATION_GROUPS,
    CROSS_GROUP_CORR,
    DEFAULT_CORR,
    DEFAULT_PARAMS,
    INTRA_FINANCE_CORR,
    INTRA_TECH_CORR,
    SEED_PRICES,
    TICKER_PARAMS,
    TSLA_CORR,
)
from .tickers import normalize_ticker, normalize_tickers

logger = logging.getLogger(__name__)


def seed_price(ticker: str) -> float:
    """Starting price for a ticker.

    Tickers without a listed seed get a value in [50, 300] derived from a stable
    hash, so re-adding one or restarting the process gives the same price.
    (The built-in hash() is randomised per process, so it cannot be used.)
    """
    if ticker in SEED_PRICES:
        return SEED_PRICES[ticker]
    digest = hashlib.sha256(ticker.encode()).digest()
    return 50.0 + (int.from_bytes(digest[:8], "big") % 25_001) / 100


class GBMSimulator:
    """Correlated geometric Brownian motion price simulator.

    S(t+dt) = S(t) * exp((mu - sigma^2/2) * dt + sigma * sqrt(dt) * Z)
    """

    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR

    def __init__(
        self,
        tickers: list[str],
        dt: float = DEFAULT_DT,
        event_probability: float = 0.001,
    ) -> None:
        self._dt = dt
        self._event_prob = event_probability
        self._tickers: list[str] = []
        self._prices: dict[str, float] = {}
        self._params: dict[str, dict[str, float]] = {}
        self._cholesky: np.ndarray | None = None

        for ticker in tickers:
            self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    def step(self) -> dict[str, float]:
        """Advance all tickers one step. Returns {ticker: new_price}."""
        n = len(self._tickers)
        if n == 0:
            return {}

        z = np.random.standard_normal(n)
        if self._cholesky is not None:
            z = self._cholesky @ z

        result: dict[str, float] = {}
        for i, ticker in enumerate(self._tickers):
            mu = self._params[ticker]["mu"]
            sigma = self._params[ticker]["sigma"]
            drift = (mu - 0.5 * sigma**2) * self._dt
            diffusion = sigma * math.sqrt(self._dt) * float(z[i])
            self._prices[ticker] *= math.exp(drift + diffusion)

            if random.random() < self._event_prob:
                magnitude = random.uniform(0.02, 0.05)
                sign = random.choice([-1, 1])
                self._prices[ticker] *= 1 + magnitude * sign
                logger.debug("Random event on %s: %.1f%%", ticker, magnitude * 100 * sign)

            result[ticker] = round(self._prices[ticker], 2)
        return result

    def add_ticker(self, ticker: str) -> None:
        if ticker in self._prices:
            return
        self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    def remove_ticker(self, ticker: str) -> None:
        if ticker not in self._prices:
            return
        self._tickers.remove(ticker)
        del self._prices[ticker]
        del self._params[ticker]
        self._rebuild_cholesky()

    def get_price(self, ticker: str) -> float | None:
        return self._prices.get(ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    def _add_ticker_internal(self, ticker: str) -> None:
        if ticker in self._prices:
            return
        self._tickers.append(ticker)
        self._prices[ticker] = seed_price(ticker)
        self._params[ticker] = dict(TICKER_PARAMS.get(ticker, DEFAULT_PARAMS))

    def _rebuild_cholesky(self) -> None:
        n = len(self._tickers)
        if n <= 1:
            self._cholesky = None
            return
        corr = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                rho = self._pairwise_correlation(self._tickers[i], self._tickers[j])
                corr[i, j] = rho
                corr[j, i] = rho
        self._cholesky = np.linalg.cholesky(corr)

    @staticmethod
    def _pairwise_correlation(t1: str, t2: str) -> float:
        tech = CORRELATION_GROUPS["tech"]
        finance = CORRELATION_GROUPS["finance"]
        if t1 == "TSLA" or t2 == "TSLA":
            return TSLA_CORR
        if t1 in tech and t2 in tech:
            return INTRA_TECH_CORR
        if t1 in finance and t2 in finance:
            return INTRA_FINANCE_CORR
        if (t1 in tech or t1 in finance) and (t2 in tech or t2 in finance):
            return CROSS_GROUP_CORR
        return DEFAULT_CORR


class SimulatorDataSource(MarketDataSource):
    """MarketDataSource that runs GBMSimulator in a background asyncio task."""

    def __init__(
        self,
        price_cache: PriceCache,
        update_interval: float = 0.5,
        event_probability: float = 0.001,
    ) -> None:
        self._cache = price_cache
        self._interval = update_interval
        self._event_prob = event_probability
        self._sim: GBMSimulator | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        if self._task is not None:
            raise RuntimeError("Simulator already started")
        self._sim = GBMSimulator(
            tickers=normalize_tickers(tickers), event_probability=self._event_prob
        )
        for ticker in self._sim.get_tickers():
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker=ticker, price=price)
        self._task = asyncio.create_task(self._run_loop(), name="simulator-loop")
        logger.info("Simulator started with %d tickers", len(self.get_tickers()))

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Simulator stopped")

    async def add_ticker(self, ticker: str) -> None:
        ticker = normalize_ticker(ticker)
        if self._sim is None:
            return
        self._sim.add_ticker(ticker)
        price = self._sim.get_price(ticker)
        if price is not None and ticker not in self._cache:
            self._cache.update(ticker=ticker, price=price)

    async def remove_ticker(self, ticker: str) -> None:
        ticker = normalize_ticker(ticker)
        if self._sim:
            self._sim.remove_ticker(ticker)
        self._cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return self._sim.get_tickers() if self._sim else []

    async def _run_loop(self) -> None:
        while True:
            try:
                if self._sim:
                    for ticker, price in self._sim.step().items():
                        self._cache.update(ticker=ticker, price=price)
            except Exception:
                logger.exception("Simulator step failed")
            await asyncio.sleep(self._interval)
```

### Key behaviors

- **Immediate seeding**: When `start()` is called, the cache is populated with seed prices *before* the loop begins. This means the SSE endpoint has data to send on its very first tick, with no blank-screen delay.
- **Graceful cancellation**: `stop()` cancels the task and awaits it, catching `CancelledError`. This ensures clean shutdown during FastAPI lifespan teardown.
- **Exception resilience**: The loop catches exceptions per-step so a single bad tick doesn't kill the entire data feed.

---

## 7. Massive API Client

**File: `backend/app/market/massive_client.py`**

Polls the Massive (formerly Polygon.io) REST API snapshot endpoint on a configurable interval. The synchronous Massive client runs in `asyncio.to_thread()` to avoid blocking the event loop.

```python
"""Massive (formerly Polygon.io) REST polling market data source."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .cache import PriceCache
from .interface import MarketDataSource
from .tickers import normalize_ticker, normalize_tickers

logger = logging.getLogger(__name__)


class MassiveDataSource(MarketDataSource):
    """Polls the Massive snapshot endpoint for all tickers in one call.

    Free tier allows 5 req/min, hence the 15s default interval.
    """

    def __init__(
        self,
        api_key: str,
        price_cache: PriceCache,
        poll_interval: float = 15.0,
    ) -> None:
        self._api_key = api_key
        self._cache = price_cache
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None
        self._client: Any = None

    async def start(self, tickers: list[str]) -> None:
        """Start polling. Returns at once; the first poll runs in the background."""
        if self._task is not None:
            raise RuntimeError("Massive poller already started")
        # Lazy import: `massive` is only required when a key is configured.
        from massive import RESTClient

        self._client = RESTClient(api_key=self._api_key)
        self._tickers = normalize_tickers(tickers)
        self._task = asyncio.create_task(self._poll_loop(), name="massive-poller")
        logger.info("Massive poller started: %d tickers", len(self._tickers))

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._client = None

    async def add_ticker(self, ticker: str) -> None:
        ticker = normalize_ticker(ticker)
        if ticker not in self._tickers:
            self._tickers.append(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        ticker = normalize_ticker(ticker)
        self._tickers = [t for t in self._tickers if t != ticker]
        self._cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    async def _poll_loop(self) -> None:
        while True:
            await self._poll_once()
            await asyncio.sleep(self._interval)

    async def _poll_once(self) -> None:
        if not self._tickers or not self._client:
            return
        try:
            snapshots = await asyncio.to_thread(
                self._fetch_snapshots, self._client, list(self._tickers)
            )
            processed = self._apply_snapshots(snapshots)
        except Exception as e:  # noqa: BLE001 - keep polling on any failure
            self.last_error = str(e)
            logger.error("Massive poll failed: %s", e)
            return

        if processed:
            self.last_success_at = time.time()
            self.last_error = None
        else:
            self.last_error = "No usable snapshots in response"
            logger.warning("Massive poll: %s", self.last_error)
        logger.debug("Massive poll: updated %d/%d tickers", processed, len(self._tickers))

    def _apply_snapshots(self, snapshots: list) -> int:
        """Write snapshots to the cache and return how many were stored."""
        processed = 0
        for snap in snapshots:
            # The ticker may have been removed while the request was in flight.
            if snap.ticker not in self._tickers:
                continue
            try:
                trade = snap.last_trade
                # SIP timestamps are in nanoseconds; the cache uses seconds.
                ns = trade.sip_timestamp
                prev_day = snap.prev_day
                self._cache.update(
                    ticker=snap.ticker,
                    price=trade.price,
                    timestamp=ns / 1e9 if ns else None,
                    reference_price=prev_day.close if prev_day else None,
                )
                processed += 1
            except (AttributeError, TypeError, ValueError) as e:
                logger.warning("Skipping snapshot for %s: %s", snap.ticker, e)
        return processed

    @staticmethod
    def _fetch_snapshots(client: Any, tickers: list[str]) -> list:
        """Synchronous API call; runs in a worker thread."""
        from massive.rest.models import SnapshotMarketType

        return client.get_snapshot_all(
            # The SDK expects the string value; passing the enum builds a wrong URL.
            market_type=SnapshotMarketType.STOCKS.value,
            tickers=tickers,
        )
```

### SDK details that matter

- Pass `SnapshotMarketType.STOCKS.value`. The enum is not a `str` subclass, and passing it builds a wrong URL.
- The trade time is `last_trade.sip_timestamp`, in **nanoseconds**. `LastTrade` has no `timestamp` attribute. The unit has not been confirmed against the live API; check it with the first real key.
- The daily reference is `prev_day.close`. `day` has no `previous_close` or `change_percent`.
- Test against real SDK models and the real `RESTClient` (stub only the HTTP server). Mocks accept any attribute name.

### Error handling philosophy

The Massive poller is intentionally resilient. `last_success_at` and `last_error` record feed health.

| Error | Behavior |
|-------|----------|
| **401 / 429 / network** | Logged, stored in `last_error`. Retried on the next interval. |
| **Unusable snapshot** (no trade, bad price) | That ticker is skipped with a warning; others are processed. |
| **No timestamp** | The current time is used. |
| **No previous day** | The existing reference price is kept (first price for a new ticker). |
| **Ticker removed during a poll** | Its snapshot is ignored. |
| **All tickers fail** | Cache retains last-known prices. |

`start()` does not wait for the first poll, so a slow API does not delay application startup.

### Lazy import strategy

`from massive import RESTClient` happens inside `start()`, so the simulator path never imports the SDK.
`massive` is still a declared dependency in `pyproject.toml`.

---

## 8. Factory

**File: `backend/app/market/factory.py`**

```python
"""Select a market data source from the environment."""

from __future__ import annotations

import logging
import os

from .cache import PriceCache
from .interface import MarketDataSource

logger = logging.getLogger(__name__)


def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    """MASSIVE_API_KEY set and non-empty -> Massive; otherwise the simulator."""
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        from .massive_client import MassiveDataSource

        logger.info("Market data source: Massive API")
        return MassiveDataSource(api_key=api_key, price_cache=price_cache)

    from .simulator import SimulatorDataSource

    logger.info("Market data source: GBM simulator")
    return SimulatorDataSource(price_cache=price_cache)
```

### Usage at app startup

```python
price_cache = PriceCache()
source = create_market_data_source(price_cache)
await source.start(initial_tickers)  # e.g., ["AAPL", "GOOGL", ...]
```

---

## 9. SSE Streaming Endpoint

**File: `backend/app/market/stream.py`**

The SSE endpoint is a FastAPI route that holds open a long-lived HTTP connection and pushes price updates to the client as `text/event-stream`.

```python
"""SSE endpoint streaming prices from the PriceCache.

The stream only ends when the client disconnects, and uvicorn waits for open
connections before running shutdown. Always run the server with
--timeout-graceful-shutdown (see planning/PLAN.md section 11).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

logger = logging.getLogger(__name__)

KEEPALIVE_SECONDS = 10.0


def create_stream_router(price_cache: PriceCache, interval: float = 0.5) -> APIRouter:
    """Build a fresh router (no shared module state) bound to the given cache."""
    router = APIRouter(prefix="/api/stream", tags=["streaming"])

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _generate_events(price_cache, request, interval),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router


async def _generate_events(
    price_cache: PriceCache,
    request: Request,
    interval: float = 0.5,
    keepalive_interval: float = KEEPALIVE_SECONDS,
) -> AsyncGenerator[str, None]:
    """Yield one aggregate `data:` event per cache change, until disconnect.

    The first event is always a full snapshot, even if empty (`{}`), so that a
    reconnecting client drops tickers that no longer exist. While nothing
    changes, an SSE comment is sent periodically to keep the connection open.
    """
    yield "retry: 1000\n\n"

    last_version = -1
    last_sent = time.monotonic()
    while not await request.is_disconnected():
        # Read the version first: a write in between only causes one extra event.
        version = price_cache.version
        if version != last_version:
            last_version = version
            payload = json.dumps({t: u.to_dict() for t, u in price_cache.get_all().items()})
            last_sent = time.monotonic()
            yield f"data: {payload}\n\n"
        elif time.monotonic() - last_sent >= keepalive_interval:
            last_sent = time.monotonic()
            yield ": keepalive\n\n"
        await asyncio.sleep(interval)
```

### SSE wire format

One aggregate, unnamed event per cache change. The first event after connecting is always a full snapshot (`{}` if empty). While nothing changes, a `: keepalive` comment is sent about every 10 s.

```
data: {"AAPL":{"ticker":"AAPL","price":190.50,"previous_price":190.42,"timestamp":1707580800.5,"change":0.08,"change_percent":0.042,"direction":"up","reference_price":190.0,"day_change_percent":0.2632}}

```

The client parses this with:

```javascript
const eventSource = new EventSource('/api/stream/prices');
eventSource.onmessage = (event) => {
    const prices = JSON.parse(event.data);  // replaces the full price set
};
```

### Shutdown

The stream ends only when the client disconnects, and uvicorn waits for open connections before running lifespan shutdown. **Always start uvicorn with `--timeout-graceful-shutdown 2`.** A `CancelledError` traceback is logged for each stream that is cut off; this is expected.

### Why poll-and-push instead of event-driven?

The SSE endpoint polls the cache on a fixed interval rather than being notified by the data source. This is simpler and produces predictable, evenly-spaced updates for the frontend. The frontend accumulates these into sparkline charts — regular spacing is important for clean visualization.

---

## 10. FastAPI Lifecycle Integration

The market data system starts and stops with the FastAPI application using the `lifespan` context manager pattern.

**In `backend/app/main.py`:**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.market.cache import PriceCache
from app.market.factory import create_market_data_source
from app.market.interface import MarketDataSource
from app.market.stream import create_stream_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown of background services."""

    # --- STARTUP ---

    # 1. Create the shared price cache
    price_cache = PriceCache()
    app.state.price_cache = price_cache

    # 2. Create and start the market data source
    source = create_market_data_source(price_cache)
    app.state.market_source = source

    # 3. Load initial tickers: the union of the watchlist and open positions
    initial_tickers = await load_tracked_tickers()  # watchlist ∪ positions, from SQLite
    await source.start(initial_tickers)

    # 4. Register the SSE streaming router
    stream_router = create_stream_router(price_cache)
    app.include_router(stream_router)

    yield  # App is running

    # --- SHUTDOWN ---
    await source.stop()


app = FastAPI(title="FinAlly", lifespan=lifespan)


# Dependency for injecting the price cache into route handlers
def get_price_cache() -> PriceCache:
    return app.state.price_cache


def get_market_source() -> MarketDataSource:
    return app.state.market_source
```

### Accessing market data from other routes

Other parts of the backend (trade execution, portfolio valuation, watchlist management) access the price cache and data source via FastAPI's dependency injection:

```python
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/api")

@router.post("/portfolio/trade")
async def execute_trade(
    trade: TradeRequest,
    price_cache: PriceCache = Depends(get_price_cache),
):
    current_price = price_cache.get_price(trade.ticker)
    if current_price is None:
        raise HTTPException(404, f"No price available for {trade.ticker}")
    # ... execute trade at current_price ...


@router.post("/watchlist")
async def add_to_watchlist(
    payload: WatchlistAdd,
    source: MarketDataSource = Depends(get_market_source),
    price_cache: PriceCache = Depends(get_price_cache),
):
    # Add to database ...
    # Then tell the data source to start tracking it
    await source.add_ticker(payload.ticker)
    # ...


@router.delete("/watchlist/{ticker}")
async def remove_from_watchlist(
    ticker: str,
    source: MarketDataSource = Depends(get_market_source),
):
    # Remove from database ...
    # Then stop tracking
    await source.remove_ticker(ticker)
    # ...
```

---

## 11. Watchlist Coordination

When the watchlist changes (via REST API or LLM chat), the market data source must be notified so it tracks the right set of tickers.

### Flow: Adding a Ticker

```
User (or LLM) → POST /api/watchlist {ticker: "PYPL"}
  → Insert into watchlist table (SQLite)
  → await source.add_ticker("PYPL")
      Simulator: adds to GBMSimulator, rebuilds Cholesky, seeds cache
      Massive: appends to ticker list, appears on next poll
  → Return success (ticker + current price if available)
```

### Flow: Removing a Ticker

```
User (or LLM) → DELETE /api/watchlist/PYPL
  → Delete from watchlist table (SQLite)
  → await source.remove_ticker("PYPL")
      Simulator: removes from GBMSimulator, rebuilds Cholesky, removes from cache
      Massive: removes from ticker list, removes from cache
  → Return success
```

### Edge case: Ticker has an open position

If the user removes a ticker from the watchlist but still holds shares, the ticker should remain in the data source so portfolio valuation stays accurate. The watchlist route should check for this:

```python
@router.delete("/watchlist/{ticker}")
async def remove_from_watchlist(
    ticker: str,
    source: MarketDataSource = Depends(get_market_source),
):
    # Remove from watchlist table
    await db.delete_watchlist_entry(ticker)

    # Only stop tracking if no open position
    position = await db.get_position(ticker)
    if position is None or position.quantity == 0:
        await source.remove_ticker(ticker)

    return {"status": "ok"}
```

---

## 12. Testing Strategy

The tests in `backend/tests/market/` are the reference. Run them with `uv run pytest` from `backend/`.

| File | Covers |
|---|---|
| `test_models.py`, `test_cache.py` | Derived fields, reference price, invalid prices, thread safety |
| `test_tickers.py` | Normalisation, rejection by both sources |
| `test_simulator.py`, `test_simulator_source.py` | GBM math, correlation, stable seed prices, lifecycle |
| `test_massive.py` | Real SDK models and `RESTClient` against a local stub HTTP server |
| `test_stream.py` | Event generator: snapshots, empty cache, keepalive |
| `test_stream_server.py` | Real uvicorn process, including shutdown with a connected client |
| `test_factory.py` | Source selection |

---

## 13. Error Handling & Edge Cases

### 13.1 Startup: Empty Watchlist

If the database has no watchlist entries (user deleted everything), `start()` receives an empty list. Both data sources handle this gracefully — the simulator produces no prices, the Massive poller skips its API call. The SSE endpoint sends one `{}` snapshot, then keepalive comments. When the user adds a ticker, the source starts tracking it immediately.

### 13.2 Price Cache Miss During Trade

If a user tries to trade a ticker that has no cached price (e.g., just added to watchlist, Massive hasn't polled yet):

```python
price = price_cache.get_price(ticker)
if price is None:
    raise HTTPException(
        status_code=400,
        detail=f"Price not yet available for {ticker}. Please wait a moment and try again.",
    )
```

The simulator avoids this by seeding the cache in `add_ticker()`. The Massive client may have a brief gap — the HTTP 400 with a clear message is the correct response.

### 13.3 Massive API Key Invalid

If the API key is set but invalid, the first poll will fail with a 401. The poller logs the error, sets `last_error` and keeps retrying. The SSE endpoint sends an empty snapshot and keepalives. The user sees no prices and a connection status indicator showing "connected" (SSE is working, just no data). The fix is to correct the API key and restart.

### 13.4 Thread Safety Under Load

The `PriceCache` uses `threading.Lock` which is a mutex — only one thread can hold it at a time. Under normal load (10 tickers, 2 updates/sec), lock contention is negligible. The critical section is tiny (dict lookup + assignment).

If this ever became a bottleneck (hundreds of tickers, many concurrent SSE readers), the fix would be a `ReadWriteLock` — but that level of optimization is unnecessary for this project.

### 13.5 Simulator Precision

GBM with tiny `dt` produces very small per-tick moves. Floating-point precision is not a concern because:
- Prices are `round()`ed to 2 decimal places in `GBMSimulator.step()`
- The exponential formulation (`exp(drift + diffusion)`) is numerically stable
- Prices are always positive (exponential function)

---

## 14. Configuration Summary

All tunable parameters and their defaults:

| Parameter | Location | Default | Description |
|-----------|----------|---------|-------------|
| `MASSIVE_API_KEY` | Environment variable | `""` (empty) | If set, use Massive API; otherwise use simulator |
| `update_interval` | `SimulatorDataSource.__init__` | `0.5` (seconds) | Time between simulator ticks |
| `poll_interval` | `MassiveDataSource.__init__` | `15.0` (seconds) | Time between Massive API polls |
| `event_probability` | `GBMSimulator.__init__` | `0.001` | Chance of a random shock event per ticker per tick |
| `dt` | `GBMSimulator.__init__` | `~8.5e-8` | GBM time step (fraction of a trading year) |
| SSE push interval | `_generate_events()` | `0.5` (seconds) | Time between SSE pushes to the client |
| `keepalive_interval` | `_generate_events()` | `10.0` (seconds) | Idle time before an SSE keepalive comment |
| `--timeout-graceful-shutdown` | uvicorn command line | set to `2` | Required so open SSE streams do not block shutdown |
| SSE retry directive | `_generate_events()` | `1000` (ms) | Browser EventSource reconnection delay |

### Package `__init__.py`

**File: `backend/app/market/__init__.py`**

```python
"""Market data subsystem for FinAlly."""

from .cache import PriceCache
from .factory import create_market_data_source
from .interface import MarketDataSource
from .models import PriceUpdate
from .stream import create_stream_router
from .tickers import InvalidTickerError, normalize_ticker

__all__ = [
    "InvalidTickerError",
    "MarketDataSource",
    "PriceCache",
    "PriceUpdate",
    "create_market_data_source",
    "create_stream_router",
    "normalize_ticker",
]
```
