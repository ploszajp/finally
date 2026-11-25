"""Massive (formerly Polygon.io) REST polling market data source."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .cache import PriceCache
from .interface import MarketDataSource

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
        # Lazy import: `massive` is only required when a key is configured.
        from massive import RESTClient

        self._client = RESTClient(api_key=self._api_key)
        self._tickers = []
        for t in tickers:
            t = t.upper().strip()
            if t not in self._tickers:
                self._tickers.append(t)
        await self._poll_once()
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
        ticker = ticker.upper().strip()
        if ticker not in self._tickers:
            self._tickers.append(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        self._tickers = [t for t in self._tickers if t != ticker]
        self._cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self._poll_once()

    async def _poll_once(self) -> None:
        if not self._tickers or not self._client:
            return
        try:
            snapshots = await asyncio.to_thread(self._fetch_snapshots)
        except Exception as e:  # noqa: BLE001 - keep polling on any failure
            logger.error("Massive poll failed: %s", e)
            return

        processed = 0
        for snap in snapshots:
            try:
                price = snap.last_trade.price
                timestamp = snap.last_trade.timestamp / 1000.0  # ms -> s
                self._cache.update(ticker=snap.ticker, price=price, timestamp=timestamp)
                processed += 1
            except (AttributeError, TypeError) as e:
                logger.warning("Skipping snapshot for %s: %s", getattr(snap, "ticker", "???"), e)
        logger.debug("Massive poll: updated %d/%d tickers", processed, len(self._tickers))

    def _fetch_snapshots(self) -> list:
        """Synchronous API call; runs in a worker thread."""
        from massive.rest.models import SnapshotMarketType

        return self._client.get_snapshot_all(
            market_type=SnapshotMarketType.STOCKS,
            tickers=list(self._tickers),
        )
