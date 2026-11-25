"""Select the market data source from environment variables."""
from __future__ import annotations

import os
from collections.abc import Mapping

from .cache import PriceCache
from .interface import MarketDataSource
from .massive import MassiveClient
from .simulator import Simulator


def create_market_source(
    cache: PriceCache, env: Mapping[str, str] | None = None
) -> MarketDataSource:
    env = os.environ if env is None else env
    key = (env.get("MASSIVE_API_KEY") or "").strip()
    if key:
        return MassiveClient(cache, key)
    return Simulator(cache)
