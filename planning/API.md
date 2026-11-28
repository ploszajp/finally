# FinAlly REST API Contract

The shared contract between the frontend, the backend, the LLM chat service and the E2E tests.
All endpoints are same-origin under `/api`. Request and response bodies are JSON (`Content-Type: application/json`).
The SSE stream `GET /api/stream/prices` is specified in `PLAN.md` §6 and is not repeated here.

Owners: backend-engineer (everything except §6), llm-engineer (§6 Chat).

---

## 1. Conventions

| Topic | Rule |
|---|---|
| Timestamps in REST bodies | ISO 8601 strings in UTC with offset, e.g. `"2026-11-28T14:03:21.512345+00:00"`. (SSE uses Unix epoch seconds, see PLAN.md §6.) |
| Money | Floats in USD. Cash and trade totals are rounded to cents (2 decimals). Prices are rounded to cents by the price cache. |
| Quantity | Floats, fractional shares allowed, rounded to 4 decimals. |
| P&L, percentages | `unrealized_pnl` rounded to 2 decimals; `*_percent` fields are percentages (5.25 means 5.25%), rounded to 2 decimals. |
| Tickers | Normalised by the backend: trimmed, upper-cased, must match `^[A-Z][A-Z.\-]{0,9}$`. The response always contains the normalised form. |
| User | Single user, `user_id = "default"`. There is no auth. |

### Error format

Every error the application raises has the body:

```json
{"detail": "Insufficient cash: need $1,905.00, have $1,200.00"}
```

`detail` is a human-readable English sentence suitable for showing in the UI as-is.

The one exception is FastAPI's own request-body validation (wrong types, missing fields), which returns **422** with FastAPI's standard shape, where `detail` is a list:

```json
{"detail": [{"type": "missing", "loc": ["body", "ticker"], "msg": "Field required", "input": {}}]}
```

Clients should display `detail` when it is a string, and a generic "Invalid request" otherwise.

### Status codes

| Code | Meaning |
|---|---|
| 200 | Success (GET, POST trade, POST chat, DELETE watchlist) |
| 201 | Created (POST watchlist) |
| 400 | Business-rule validation failed: malformed ticker, `quantity <= 0`, insufficient cash, insufficient shares, no price available for the ticker |
| 404 | Ticker not on the watchlist (DELETE) |
| 409 | Ticker already on the watchlist (POST) |
| 422 | Request body does not match the schema (FastAPI default) |
| 500 | Unexpected server error (`{"detail": "Internal server error"}`) |

---

## 2. Health

### `GET /api/health`

```json
{
  "status": "ok",
  "market_data_source": "simulator",
  "tracked_tickers": 10,
  "last_success_at": null,
  "last_error": null
}
```

- `market_data_source`: `"simulator"` or `"massive"`.
- `last_success_at` (Unix seconds, float) and `last_error` (string) are only filled by the Massive source; the simulator leaves both `null`.
- Always 200 while the process is up. Used by Docker `HEALTHCHECK` and the E2E tests to wait for readiness.

---

## 3. Portfolio

### `GET /api/portfolio`

```json
{
  "cash_balance": 8095.0,
  "positions_value": 1912.4,
  "total_value": 10007.4,
  "unrealized_pnl": 7.4,
  "unrealized_pnl_percent": 0.39,
  "positions": [
    {
      "ticker": "AAPL",
      "quantity": 10.0,
      "avg_cost": 190.5,
      "current_price": 191.24,
      "market_value": 1912.4,
      "unrealized_pnl": 7.4,
      "pnl_percent": 0.39,
      "weight_percent": 19.11
    }
  ]
}
```

| Field | Definition |
|---|---|
| `current_price` | Latest price from the price cache. If the cache has no price (rare: Massive not yet polled), it falls back to `avg_cost` so valuation never breaks. |
| `market_value` | `quantity * current_price` |
| `unrealized_pnl` | `(current_price - avg_cost) * quantity` |
| `pnl_percent` | `(current_price - avg_cost) / avg_cost * 100`. This is the "% change" column of the positions table (PLAN.md §13 item 9). |
| `weight_percent` | `market_value / total_value * 100`. Sizes the heatmap rectangles. |
| `positions_value` | Sum of `market_value` |
| `total_value` | `cash_balance + positions_value` |
| `unrealized_pnl` (top level) | Sum of position `unrealized_pnl` |
| `unrealized_pnl_percent` | Top-level `unrealized_pnl` / total cost basis * 100 (0 when there are no positions) |

`positions` is sorted by ticker. It is empty (`[]`) when nothing is held. The frontend can revalue positions live from SSE prices between fetches using the same formulas.

### `POST /api/portfolio/trade`

Market order, instant fill at the current cached price, no fees.

Request:

```json
{"ticker": "aapl", "quantity": 10, "side": "buy"}
```

- `side`: `"buy"` or `"sell"` (anything else → 422).
- `quantity`: number > 0, rounded to 4 decimals before validation; if it rounds to 0 → 400.

Response **200**:

```json
{
  "trade": {
    "id": "6f1c2a8e-4d0b-4f6e-9b7a-2f0c1d3e4a5b",
    "ticker": "AAPL",
    "side": "buy",
    "quantity": 10.0,
    "price": 190.5,
    "total": 1905.0,
    "executed_at": "2026-11-28T14:03:21.512345+00:00"
  },
  "portfolio": { "...": "same shape as GET /api/portfolio, after the trade" }
}
```

Errors (**400**, `{"detail": "..."}`), exact wording may vary:

| Case | Example `detail` |
|---|---|
| Malformed ticker | `"Invalid ticker: '12AB'"` |
| Quantity not positive after rounding | `"Quantity must be greater than 0"` |
| No price in the cache | `"No price available for ZZZZ. Add it to the watchlist first."` |
| Insufficient cash (buy) | `"Insufficient cash: need $1,905.00, have $1,200.00"` |
| Insufficient shares (sell) | `"Insufficient shares: trying to sell 15 AAPL, have 10"` |

#### Trade execution rules

1. Normalise the ticker; round `quantity` to 4 decimals; reject `<= 0`.
2. Price = `price_cache.get_price(ticker)`; no price → 400. Only tickers in the tracked set (watchlist ∪ positions) have prices, so to trade a new symbol add it to the watchlist first.
3. `total = round(price * quantity, 2)`.
4. Inside **one SQLite transaction** (`BEGIN IMMEDIATE`), read cash and the position, validate, then write:
   - **Buy**: requires `cash >= total`. `cash -= total`. New `avg_cost = (old_qty * old_avg + quantity * price) / (old_qty + quantity)`; new quantity rounded to 4 decimals.
   - **Sell**: requires `position_qty >= quantity` (with a 1e-9 tolerance). `cash += total`. `avg_cost` is **unchanged** on a partial sell. If the remaining quantity rounds to 0, the position row is **deleted**.
   - Append a row to `trades`.
   - Cash is stored rounded to cents.
5. After commit: record a portfolio snapshot. If a sell closed a position in a ticker that is **not** on the watchlist, call `source.remove_ticker(ticker)` (PLAN.md §6).

Concurrent trades (manual + LLM) are serialised by the SQLite write lock, so cash cannot be spent twice.

### `GET /api/portfolio/history`

Portfolio value snapshots for the P&L chart, oldest first.

```json
{
  "snapshots": [
    {"total_value": 10000.0, "recorded_at": "2026-11-28T14:00:00.000000+00:00"},
    {"total_value": 10007.4, "recorded_at": "2026-11-28T14:00:30.000000+00:00"}
  ]
}
```

- A snapshot is recorded once at startup (so the chart is never empty), every 30 seconds by a background task, and immediately after every trade.
- Optional query parameter `limit` (default 1000, max 5000) returns the most recent N snapshots, still ordered oldest first.

---

## 4. Watchlist

### `GET /api/watchlist`

Ordered by `added_at` (oldest first, so the default ten keep their seed order).

```json
{
  "watchlist": [
    {
      "ticker": "AAPL",
      "price": 191.24,
      "previous_price": 191.2,
      "change_percent": 0.0209,
      "day_change_percent": 0.39,
      "direction": "up",
      "added_at": "2026-11-28T14:00:00.000000+00:00"
    }
  ]
}
```

- Price fields mirror the SSE fields of the same name (PLAN.md §6). They are `null` when the cache has no price yet (`direction` is then `"flat"`).
- Live updates come from SSE; this endpoint is for the initial load and after changes.

### `POST /api/watchlist`

Request:

```json
{"ticker": "pypl"}
```

Response **201**: one watchlist item, same shape as an element of `GET /api/watchlist` (the price is usually already filled, because the simulator seeds a price when a ticker is added).

```json
{"ticker": "PYPL", "price": 68.12, "previous_price": 68.12, "change_percent": 0.0, "day_change_percent": 0.0, "direction": "flat", "added_at": "2026-11-28T14:05:00.000000+00:00"}
```

Errors: **400** malformed ticker, **409** `{"detail": "PYPL is already on the watchlist"}`.

Side effect: `source.add_ticker(ticker)` (no-op if already tracked because of a position).

### `DELETE /api/watchlist/{ticker}`

The path ticker is normalised the same way (`/api/watchlist/aapl` works).

Response **200**:

```json
{"ticker": "PYPL", "removed": true}
```

Errors: **400** malformed ticker, **404** `{"detail": "PYPL is not on the watchlist"}`.

Side effect: `source.remove_ticker(ticker)` **only if no position is open** in that ticker; otherwise the ticker stays tracked (and priced) for valuation.

---

## 5. Static frontend

Every path that does not start with `/api` serves the Next.js static export (`STATIC_DIR`, default `backend/static`, in Docker `/app/static`). Unknown non-API paths fall back to `index.html` (SPA). Unknown `/api/...` paths return 404 JSON `{"detail": "Not Found"}`.

---

## 6. Chat

The full chat contract is in **`planning/API_CHAT.md`** (owned by llm-engineer): `ChatMessage` shape, per-action results, LLM failure handling, structured output schema and the deterministic `LLM_MOCK=true` rules. Summary:

### `POST /api/chat`

Request: `{"message": "Buy 5 shares of NVDA"}` (trimmed, 1 to 2000 chars, else 422).

Response **200**: `{"user_message": ChatMessage, "assistant_message": ChatMessage}`. The assistant message's `actions` holds `watchlist_changes[]` and `trades[]`, each with `status` (`"executed"` / `"rejected"`) and `error` (reason or `null`), plus `actions.error` (`null` or an LLM failure code). LLM failures (missing key, timeout, network, invalid output) still return **200** with `actions.error` set and a friendly `content`; there is no 503.

### `GET /api/chat/history`

Query `limit` (default 50, max 200). Response **200**: `{"messages": [ChatMessage, ...]}`, oldest first. Resolves PLAN.md §13 item 7.

---

## 7. Resolved decisions from PLAN.md §13

| Item | Decision |
|---|---|
| 1 — API response shapes | This document. |
| 6 — LLM error handling | §6 Chat (llm-engineer). The app starts without `OPENROUTER_API_KEY`; only chat is affected. |
| 7 — Chat history endpoint | `GET /api/chat/history`, §6. |
| 8a — Volume | Named volume only: `docker run -v finally-data:/app/db ...`. The repo's top-level `db/` is used only for local (non-Docker) runs, where the backend writes `db/finally.db` relative to the project root. The DB path is configurable with `DB_PATH`. |
| 8b — `.env` | The container gets variables via `--env-file .env` (or compose `env_file`). The backend reads only `os.environ`. For local development it additionally loads the project-root `.env` with python-dotenv if the file exists (never overriding already-set variables). |
| 8c — DB init | Once at startup in the FastAPI lifespan: create schema if missing, seed if empty, then record the first portfolio snapshot. No lazy per-request init. |
| 8d — Charts | Frontend: Lightweight Charts (canvas) for the main chart, sparklines may be SVG/canvas; the heatmap is a treemap built from `div`s (testable in E2E). |
| 10 — Trade validation | §3 "Trade execution rules". |

### Environment variables read by the backend

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | LLM chat. Missing → chat replies with a friendly error (200, `actions.error` set); the rest works. |
| `MASSIVE_API_KEY` | empty | Non-empty → Massive market data, else simulator. |
| `LLM_MOCK` | `false` | `true` → deterministic mock LLM (§6). |
| `DB_PATH` | `<project root>/db/finally.db` locally; `/app/db/finally.db` in Docker | SQLite file location. |
| `STATIC_DIR` | `backend/static` | Next.js export directory. App starts without it (API only). |
