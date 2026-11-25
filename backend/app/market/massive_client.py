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
