# Backend

FastAPI backend, managed as a `uv` project. The specification is `../planning/PLAN.md`. Only the market data subsystem (`app/market/`) exists so far; see `../planning/MARKET_DATA_SUMMARY.md`.

## Commands

Run from `backend/`.

```bash
uv sync                           # install dependencies
uv run pytest                     # tests
uv run ruff check .               # lint
uv run ruff format --check .      # format check
uv run market_data_demo.py        # live terminal demo
```

Add dependencies with `uv add` (`uv add --dev` for development tools) and commit `uv.lock`.

## Using market data

Import from `app.market`, which exports the public API.

```python
from app.market import PriceCache, create_market_data_source, create_stream_router

cache = PriceCache()
source = create_market_data_source(cache)
await source.start(tickers)  # watchlist ∪ open positions
router = create_stream_router(cache)
...
await source.stop()
```

- Read prices from the cache (`get`, `get_price`, `get_all`). Only data sources write to it.
- `cache.get_price()` returns `None` for a ticker with no price; handle that before trading or valuing.
- `remove_ticker()` also drops the cached price, so never call it while a position is open.
- Validate tickers with `normalize_ticker()`. Map `InvalidTickerError` to HTTP 400.
- Run uvicorn with `--timeout-graceful-shutdown 2`, or open SSE connections block shutdown.

## Tests

Tests live in `tests/`. `asyncio_mode` is `auto`, so async tests need no marker. Massive tests use the real SDK models and client against a stub HTTP server; do not replace the SDK with fakes or mocks, which previously hid real bugs.
