"""GBM market simulator with sector correlation and random events."""
from __future__ import annotations

import asyncio
import math
import random
import zlib
from collections.abc import Iterable

from .cache import PriceCache
from .interface import MarketDataSource

SEED_PRICES: dict[str, float] = {
    "AAPL": 190.0, "GOOGL": 175.0, "MSFT": 420.0, "AMZN": 180.0,
    "TSLA": 250.0, "NVDA": 480.0, "META": 500.0, "JPM": 195.0,
    "V": 275.0, "NFLX": 600.0,
}
# (annual drift, annual volatility)
PARAMS: dict[str, tuple[float, float]] = {
    "AAPL": (0.08, 0.25), "GOOGL": (0.08, 0.28), "MSFT": (0.09, 0.25),
    "AMZN": (0.09, 0.30), "TSLA": (0.05, 0.55), "NVDA": (0.12, 0.50),
    "META": (0.09, 0.35), "JPM": (0.06, 0.22), "V": (0.07, 0.20),
    "NFLX": (0.08, 0.38),
}
DEFAULT_PARAMS = (0.07, 0.30)
SECTORS: dict[str, str] = {
    "AAPL": "tech", "GOOGL": "tech", "MSFT": "tech", "AMZN": "tech",
    "TSLA": "tech", "NVDA": "tech", "META": "tech", "NFLX": "tech",
    "JPM": "fin", "V": "fin",
}
SECTOR_CORR = 0.6  # correlation between tickers of the same sector
TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600


def seed_price(ticker: str) -> float:
    """Known seed price, or a deterministic pseudo-random one in 20..500."""
    if ticker in SEED_PRICES:
        return SEED_PRICES[ticker]
    return float(20 + zlib.crc32(ticker.encode()) % 48000 / 100)


class Simulator(MarketDataSource):
    def __init__(
        self,
        cache: PriceCache,
        interval: float = 0.5,
        event_prob: float = 0.002,
        seed: int | None = None,
        sim_speed: float = 1.0,
    ) -> None:
        super().__init__(cache)
        self.interval = interval
        self.event_prob = event_prob  # per ticker per tick
        # Time scaling: dt in years per tick. sim_speed>1 makes moves bigger.
        self._dt = interval * sim_speed / TRADING_SECONDS_PER_YEAR
        self._rng = random.Random(seed)
        self._prices: dict[str, float] = {}
        self._task: asyncio.Task | None = None

    async def _on_added(self, ticker: str) -> None:
        self._prices[ticker] = seed_price(ticker)
        # Price is available immediately after add_ticker().
        self.cache.update(ticker, self._prices[ticker])

    async def remove_ticker(self, ticker: str) -> None:
        await super().remove_ticker(ticker)
        self._prices.pop(ticker.strip().upper(), None)

    def step(self) -> None:
        """Advance every tracked ticker by one tick and write to cache."""
        rng = self._rng
        market = rng.gauss(0, 1)
        sector_z = {s: rng.gauss(0, 1) for s in set(SECTORS.values()) | {"other"}}
        rho = SECTOR_CORR
        for t in sorted(self._tickers):
            mu, sigma = PARAMS.get(t, DEFAULT_PARAMS)
            sector = sector_z[SECTORS.get(t, "other")]
            z = math.sqrt(rho) * sector + math.sqrt(1 - rho) * rng.gauss(0, 1)
            # small global market component
            z = 0.9 * z + math.sqrt(1 - 0.81) * market
            price = self._prices[t]
            price *= math.exp((mu - 0.5 * sigma**2) * self._dt
                              + sigma * math.sqrt(self._dt) * z)
            if rng.random() < self.event_prob:
                price *= 1 + rng.choice((-1, 1)) * rng.uniform(0.02, 0.05)
            price = max(price, 0.01)
            self._prices[t] = price
            self.cache.update(t, round(price, 4))

    async def start(self, tickers: Iterable[str] = ()) -> None:
        if self._task is not None:
            return
        for t in tickers:
            await self.add_ticker(t)
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            self.step()

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
