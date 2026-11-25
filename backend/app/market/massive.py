"""Massive (Polygon.io) REST polling client."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

import httpx

from .cache import PriceCache
from .interface import MarketDataSource

log = logging.getLogger(__name__)
BASE_URL = "https://api.massive.com"
SNAPSHOT_PATH = "/v2/snapshot/locale/us/markets/stocks/tickers"


def parse_snapshot(payload: dict) -> dict[str, dict]:
    """Parse a snapshot response into {ticker: {price, open_price, timestamp}}.

    Price = last trade, falling back to day close, then previous close.
    open_price = previous day close (reference for daily change). Entries
    without a usable price are skipped. timestamp is epoch seconds.
    """
    out: dict[str, dict] = {}
    for item in payload.get("tickers") or []:
        try:
            ticker = item["ticker"]
        except (KeyError, TypeError):
            continue
        prev = (item.get("prevDay") or {}).get("c") or 0
        price = (
            (item.get("lastTrade") or {}).get("p")
            or (item.get("day") or {}).get("c")
            or prev
        )
        if not isinstance(price, (int, float)) or price <= 0:
            continue
        updated = item.get("updated")  # nanoseconds since epoch
        ts = updated / 1e9 if isinstance(updated, (int, float)) and updated > 0 else None
        out[ticker] = {
            "price": float(price),
            "open_price": float(prev) if prev and prev > 0 else None,
            "timestamp": ts,
        }
    return out


class MassiveClient(MarketDataSource):
    def __init__(
        self,
        cache: PriceCache,
        api_key: str,
        poll_interval: float = 15.0,
        base_url: str = BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(cache)
        self.api_key = api_key
        self.poll_interval = poll_interval
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=10.0)
        self._owns_client = client is None
        self._task: asyncio.Task | None = None

    async def poll_once(self) -> int:
        """Fetch one snapshot for all tracked tickers. Returns #updated."""
        if not self._tickers:
            return 0
        resp = await self._client.get(
            SNAPSHOT_PATH,
            params={"tickers": ",".join(sorted(self._tickers)), "apiKey": self.api_key},
        )
        resp.raise_for_status()
        data = parse_snapshot(resp.json())
        n = 0
        for ticker, d in data.items():
            if ticker not in self._tickers:
                continue
            self.cache.update(ticker, d["price"], d["timestamp"], d["open_price"])
            n += 1
        return n

    async def _on_added(self, ticker: str) -> None:
        # Best effort: make the price available right away when running.
        if self._task is not None:
            try:
                await self.poll_once()
            except Exception as e:  # noqa: BLE001
                log.warning("Massive poll after add failed: %s", e)

    async def start(self, tickers: Iterable[str] = ()) -> None:
        if self._task is not None:
            return
        for t in tickers:
            await self.add_ticker(t)
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - keep polling on errors
                log.warning("Massive poll failed: %s", e)
            await asyncio.sleep(self.poll_interval)

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self._owns_client:
            await self._client.aclose()
