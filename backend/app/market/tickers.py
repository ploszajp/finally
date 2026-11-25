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
