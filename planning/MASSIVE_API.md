# Massive API Reference (formerly Polygon.io)

Reference documentation for the Massive (formerly Polygon.io) REST API as used in FinAlly.

## Overview

- **Base URL**: `https://api.massive.com` (legacy `https://api.polygon.io` still supported)
- **Python package**: `massive` (install via `pip install -U massive` / `uv add massive`)
- **Min Python version**: 3.9+
- **Auth**: API key via `MASSIVE_API_KEY` env var or passed to `RESTClient(api_key=...)`
- **Auth header**: `Authorization: Bearer <API_KEY>` (the client handles this automatically)

## Rate Limits

| Tier | Limit |
|------|-------|
| Free | 5 requests/minute |
| Paid (all tiers) | Unlimited (recommended: stay under 100 req/s) |

For FinAlly, we poll on a timer. Free tier: poll every 15s. Paid: poll every 2-5s.

## Client Initialization

```python
from massive import RESTClient

# Reads MASSIVE_API_KEY from environment automatically
client = RESTClient()

# Or pass explicitly
client = RESTClient(api_key="your_key_here")
```

## Endpoints Used in FinAlly

### 1. Snapshot — All Tickers (Primary Endpoint)

Gets current prices for multiple tickers in a **single API call**. This is the main endpoint we use for polling.

**REST**: `GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,GOOGL,MSFT`

**Python client**:
```python
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

client = RESTClient()

# Get snapshots for specific tickers (one API call)
snapshots = client.get_snapshot_all(
    market_type=SnapshotMarketType.STOCKS.value,  # the string; the enum builds a wrong URL
    tickers=["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"],
)

for snap in snapshots:
    print(f"{snap.ticker}: ${snap.last_trade.price}")
    print(f"  Day change: {snap.todays_change_percent}%")
    print(f"  Previous close: {snap.prev_day.close}")
    print(f"  Day OHLC: O={snap.day.open} H={snap.day.high} L={snap.day.low} C={snap.day.close}")
    print(f"  Volume: {snap.day.volume}")
```

**Response structure** (per ticker, wire format as mapped by the SDK's `from_dict` methods in `massive` 2.12.0; abridged, illustrative values):
```json
{
  "ticker": "AAPL",
  "todaysChange": -4.54,
  "todaysChangePerc": -3.50,
  "day": {"o": 129.61, "h": 130.15, "l": 125.07, "c": 125.07, "v": 111237700, "vw": 127.35},
  "prevDay": {"c": 129.61},
  "lastTrade": {"p": 125.07, "s": 100, "x": 4, "t": 1675190399000000000},
  "lastQuote": {"p": 125.06, "s": 5, "P": 125.08, "S": 10, "t": 1675190399500000000}
}
```

In `lastQuote`, lower-case `p`/`s` are the bid and upper-case `P`/`S` the ask.

**Key fields we extract** (Python attribute names):
- `last_trade.price` — current price for trading and display
- `last_trade.sip_timestamp` — trade time in **nanoseconds** (there is no `last_trade.timestamp`; confirm the unit with the first live call)
- `prev_day.close` — reference price for the daily change (`day` has no `previous_close`)

### 2. Single Ticker Snapshot

For getting detailed data on one ticker (e.g., when user clicks a ticker for the detail view).

**Python client**:
```python
snapshot = client.get_snapshot_ticker(
    market_type=SnapshotMarketType.STOCKS.value,
    ticker="AAPL",
)

print(f"Price: ${snapshot.last_trade.price}")
print(f"Bid/Ask: ${snapshot.last_quote.bid_price} / ${snapshot.last_quote.ask_price}")
print(f"Day range: ${snapshot.day.low} - ${snapshot.day.high}")
```

### 3. Previous Close

Gets the previous day's OHLC for a ticker. Useful for seed prices.

**REST**: `GET /v2/aggs/ticker/{ticker}/prev`

**Python client**:
```python
prev = client.get_previous_close_agg(ticker="AAPL")

for agg in prev:
    print(f"Previous close: ${agg.close}")
    print(f"OHLC: O={agg.open} H={agg.high} L={agg.low} C={agg.close}")
    print(f"Volume: {agg.volume}")
```

**Response**:
```json
{
  "ticker": "AAPL",
  "results": [
    {
      "o": 150.0,
      "h": 155.0,
      "l": 149.0,
      "c": 154.5,
      "v": 1000000,
      "t": 1672531200000
    }
  ]
}
```

### 4. Aggregates (Bars)

Historical OHLCV bars over a date range. Not needed for live polling but useful if we add historical charts.

**REST**: `GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}`

**Python client**:
```python
aggs = []
for a in client.list_aggs(
    ticker="AAPL",
    multiplier=1,
    timespan="day",
    from_="2024-01-01",
    to="2024-01-31",
    limit=50000,
):
    aggs.append(a)

for a in aggs:
    print(f"Date: {a.timestamp}, O={a.open} H={a.high} L={a.low} C={a.close} V={a.volume}")
```

**Response** (each bar):
```json
{
  "o": 130.0,
  "h": 132.5,
  "l": 129.8,
  "c": 131.2,
  "v": 50000000,
  "t": 1672531200000
}
```

### 5. Last Trade / Last Quote

Individual endpoints for the most recent trade or NBBO quote.

```python
# Last trade
trade = client.get_last_trade(ticker="AAPL")
print(f"Last trade: ${trade.price} x {trade.size}")

# Last NBBO quote
quote = client.get_last_quote(ticker="AAPL")
print(f"Bid: ${quote.bid_price} x {quote.bid_size}")
print(f"Ask: ${quote.ask_price} x {quote.ask_size}")
```

## How FinAlly Uses the API

The Massive poller runs as a background task:

1. Collects all tickers from the watchlist
2. Calls `get_snapshot_all()` with those tickers (one API call)
3. Extracts `last_trade.price`, `last_trade.sip_timestamp` and `prev_day.close` from each snapshot
4. Writes to the shared in-memory price cache
5. Sleeps for the poll interval, then repeats

```python
import asyncio
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

async def poll_massive(api_key: str, get_tickers, price_cache, interval: float = 15.0):
    """Poll Massive API and update the price cache."""
    client = RESTClient(api_key=api_key)

    while True:
        tickers = get_tickers()
        if tickers:
            snapshots = client.get_snapshot_all(
                market_type=SnapshotMarketType.STOCKS.value,
                tickers=tickers,
            )
            for snap in snapshots:
                price_cache.update(
                    ticker=snap.ticker,
                    price=snap.last_trade.price,
                    reference_price=snap.prev_day.close,
                    timestamp=snap.last_trade.sip_timestamp / 1e9,
                )

        await asyncio.sleep(interval)
```

## Error Handling

The client raises exceptions for HTTP errors:
- **401**: Invalid API key
- **403**: Insufficient permissions (plan doesn't include the endpoint)
- **429**: Rate limit exceeded (free tier: 5 req/min)
- **5xx**: Server errors (client has built-in retry with 3 retries by default)

## Notes

- The snapshot endpoint returns data for **all requested tickers in one call** — this is critical for staying within rate limits on the free tier
- Timestamp units differ by endpoint: aggregate bars use Unix milliseconds, trade and quote SIP timestamps use nanoseconds
- During market closed hours, `last_trade.price` reflects the last traded price (may include after-hours)
- The `day` object resets at market open; during pre-market, values may be from the previous session
