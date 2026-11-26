# Market Data Backend — Summary

The market data subsystem in `backend/app/market/` is built. The simulator is usable; the Massive client has not been run against the live API.

## How it fits together

A `MarketDataSource` writes prices into a shared `PriceCache`. Consumers read the cache and do not know which source is active.

```
SimulatorDataSource ┐
                    ├─> PriceCache ─> GET /api/stream/prices (SSE)
MassiveDataSource   ┘
```

| Module | Role |
|---|---|
| `models.py` | `PriceUpdate`, an immutable price snapshot with derived change fields |
| `cache.py` | `PriceCache`, thread-safe latest price per ticker, with a version counter |
| `interface.py` | `MarketDataSource` abstract base class |
| `factory.py` | Picks Massive if `MASSIVE_API_KEY` is non-empty, otherwise the simulator |
| `simulator.py`, `seed_prices.py` | Correlated GBM, updated every 0.5 s, with occasional 2–5% jumps |
| `massive_client.py` | REST snapshot polling, every 15 s by default |
| `stream.py` | SSE router factory |
| `tickers.py` | Ticker normalisation and format validation |

## Contract

`PLAN.md` §6 defines the SSE event format, tracked-ticker rules and shutdown flag.

## Remaining work for the API layer

- Pass the union of watchlist and open-position tickers to `start()`.
- Do not call `remove_ticker()` while a position is open.
- Map `InvalidTickerError` to HTTP 400.
- Include the stream router from `create_stream_router(cache)` in the FastAPI app.
- Run uvicorn with `--timeout-graceful-shutdown 2`, including in the Dockerfile.
- Optionally report `last_success_at` and `last_error` in `/api/health` (Massive only).

## Known limits

- No call to the live Massive API has been made. The nanosecond timestamp unit and plan access need checking with a real key.
- Simulator prices are not restored after a restart.

## Try it

From `backend/`:

```bash
uv run market_data_demo.py --duration 30
uv run pytest
```

## Related documents

`MARKET_DATA_DESIGN.md`, `MARKET_INTERFACE.md`, `MARKET_SIMULATOR.md` and `MASSIVE_API.md` hold design detail. `MARKET_DATA_REVIEW.md` records the code review and, in §9, how each finding was resolved.
