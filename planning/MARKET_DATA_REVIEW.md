# Market Data Backend — Code Review

**Date:** 2026-11-25
**Reviewed:** commit `58f7bc4`: `backend/app/market/` (9 files), `backend/tests/market/` (7 test modules), `backend/pyproject.toml`
**Read against:** `PLAN.md`, `MARKET_DATA_DESIGN.md`, `MARKET_INTERFACE.md`, `MARKET_SIMULATOR.md`, `MASSIVE_API.md`
**Replaces:** the earlier review in this file (see §7 for the status of its findings)

---

## 1. Verdict

| Path | Status |
|---|---|
| Simulator (default) | **Usable.** Fix the shutdown hang (H1) when the app and Docker are wired up. |
| Massive (real data) | **Does not work.** Two independent bugs (C1, C2), and either one alone means no price ever reaches the cache. |

All tests pass, but they do not catch C1 or C2. The Massive tests replace the SDK with a hand-written fake and `MagicMock` snapshots, which repeat the same wrong assumptions as the code.

---

## 2. Test results

Run on a copy of `backend/` outside the repo: Python 3.13.17, `uv sync` with no lockfile, `massive` 2.12.0, numpy 2.5.5, FastAPI 0.165.0, pytest 9.2.0.

| Check | Result |
|---|---|
| `uv sync` | Succeeds |
| `pytest` | **60 passed, 0 failed** (1.7 s) |
| 20 repeated `pytest` runs | 60 passed every time |
| `ruff check` | Clean |
| `ruff format --check` | 3 files would be reformatted: `test_massive.py`, `test_models.py`, `test_stream.py` |
| Warnings | `pytest-asyncio`: `asyncio_default_fixture_loop_scope` is unset |

Coverage (line and branch): **98 % overall**.

| Module | Coverage | Not covered |
|---|---|---|
| `cache.py`, `factory.py`, `interface.py`, `models.py`, `seed_prices.py` | 100 % | |
| `massive_client.py` | 100 % | Fully covered, yet non-functional (C1, C2) |
| `simulator.py` | 97 % | line 104 and a few partial branches |
| `stream.py` | 95 % | the `CancelledError` handler (lines 58–59) |

Extra checks beyond the test suite:

- The real `massive` `RESTClient` pointed at a local stub HTTP server.
- A real uvicorn process serving the SSE router, with streaming and `SIGTERM`.
- Scripted probes for the behaviours in §3.

No request was sent to the live Massive API (no key was used). The stub payload follows the field mapping in the installed SDK's `from_dict` methods.

---

## 3. Findings

### Critical

#### C1. Wrong market type argument produces an invalid URL
`massive_client.py:101`

The code passes the enum `SnapshotMarketType.STOCKS`. In `massive` 2.12.0 this is a plain `Enum`, not a `str` subclass, and the SDK expects its string value. The real client requested:

```
/v2/snapshot/locale/global/markets/SnapshotMarketType.STOCKS/tickers   (actual)
/v2/snapshot/locale/us/markets/stocks/tickers                          (expected)
```

Against the live API this request should fail on every poll. The poller only logs the error, so the app would run with no prices.

**Fix:** pass `market_type=SnapshotMarketType.STOCKS.value` (or `"stocks"`).

#### C2. `LastTrade` has no `timestamp` attribute
`massive_client.py:89`

The SDK maps the trade time to `sip_timestamp`. With a valid response, every snapshot is rejected:

```
WARNING Skipping snapshot for AAPL: 'LastTrade' object has no attribute 'timestamp'
cache: {}
```

The unit is also wrong. The code divides by 1000 (milliseconds), but stock trade SIP timestamps are in **nanoseconds**.

**Fix:** `timestamp = snap.last_trade.sip_timestamp / 1e9`. Confirm the unit with one live call once a key is available. A missing timestamp should preferably fall back to the current time instead of dropping a valid price.

**Verification of C1 + C2:** with both changes applied to the scratch copy, the real SDK requested the correct URL and cached `AAPL 190.5` with timestamp `1707580800.0`. The repo code was not modified.

#### C3. The Massive tests enforce the wrong SDK contract
`tests/market/test_massive.py:11-42`

- `snap()` is a `MagicMock` that sets `last_trade.timestamp`. A mock accepts any attribute name.
- `fake_massive` defines `SnapshotMarketType.STOCKS` as the string `"stocks"`, while the real value is an enum member.

With the correct fix applied, 3 tests fail (`test_timestamp_ms_to_seconds`, `test_start_polls_immediately_and_stop`, `test_poll_loop_repolls`). They must change together with the fix.

**Fix:** `massive` is a declared core dependency, so build snapshots with `TickerSnapshot.from_dict(<wire JSON>)` and use the real enum. Mock only the HTTP boundary (`client._get` or a stub server) and assert the request path. Delete the fake module.

**The planning docs are the source of these bugs** and should be corrected too, or an agent may reintroduce them:

- `MARKET_DATA_DESIGN.md` §7 and §12.4, plus the sketches in `MARKET_INTERFACE.md` and `MASSIVE_API.md`, use the enum and `last_trade.timestamp` in milliseconds.
- `MASSIVE_API.md` also reads `day.previous_close` and `day.change_percent`. The SDK's `day` object (`Agg`) has neither. It offers `prev_day.close` and `todays_change_percent` on the snapshot instead.

### High

#### H1. An open SSE connection blocks server shutdown
`stream.py:47-57`

The generator ends only when the client disconnects. Under a real uvicorn, `SIGTERM` with one client connected left the server at `Waiting for connections to close`. It was still running after 6 s and exited only when the client gave up. The lifespan shutdown, including `source.stop()`, runs only after that.

With a browser tab open, Ctrl+C will appear to hang, and `docker stop` will likely end in `SIGKILL` after its 10 s grace period. That skips any later cleanup, such as closing the database.

**Fix:** start uvicorn with `--timeout-graceful-shutdown 2` (put this in the Dockerfile `CMD`). Tested: the server exited and the lifespan shutdown ran. It logs a `CancelledError` traceback, which is harmless. A quieter option is a shutdown event that the generator checks, but it must be set by a signal hook, because lifespan shutdown runs too late.

### Medium

#### M1. A removed ticker can reappear in the cache (Massive)
`massive_client.py:80-90`

If `remove_ticker()` runs while a poll is in flight, the response still contains the ticker and writes it back. Reproduced: tracked `['AAPL']`, cached `['AAPL', 'TSLA']`. The ghost entry is never updated again, but SSE keeps sending it, and trades could fill at that stale price.

**Fix:** after the `await`, skip any snapshot whose ticker is no longer in `self._tickers`.

#### M2. SSE never reports an empty price set
`stream.py:54`

`if prices:` suppresses the event when the last ticker is removed. Connected clients receive nothing and keep showing it. Reproduced.

**Fix:** after the first data event, send `data: {}` when the cache becomes empty.

#### M3. No daily change reference
`models.py`, `massive_client.py`

PLAN §2 and §10 require a **daily change %** in the watchlist. `change_percent` is the change since the previous tick (about 500 ms in the simulator, one poll in Massive). A frontend agent could easily display it as the daily figure. Neither source exposes a session open or previous close.

**Fix:** resolve PLAN §13 #9. For example, add `reference_price` to `PriceUpdate` (simulator: the first price of the session; Massive: `prev_day.close`) and serialise it, preferably before the frontend is built.

#### M4. Tickers are not validated
`simulator.py:153,175`, `massive_client.py:40,59`

Input is trimmed and upper-cased, but `""`, `"   "` and `"NOT A TICKER!!"` are accepted. The simulator invents a price for them, so they become tradable. With Massive they are added to the shared request.

**Fix:** decide PLAN §13 #10 and use one normalise-and-validate function (for example `^[A-Z][A-Z.\-]{0,9}$`) in both sources and the future API routes. Return or raise something the route can turn into a 400.

#### M5. Unknown tickers get a new random price after re-adding or restarting
`simulator.py:106`

Probe: `PYPL` was 69.26; after remove and re-add it was 96.82, a 40 % jump. Once positions are persisted, a restart will create arbitrary gains or losses for any non-seed ticker. Seed tickers also reset to their seed price.

**Fix:** derive the seed from a stable hash of the ticker (use `hashlib`, not `hash()`). Decide separately whether to restore last prices from the database.

**Integration requirement:** `remove_ticker()` also deletes the cached price. The watchlist route must not call it while a position is open (`MARKET_DATA_DESIGN.md` §11, PLAN §13 #3), and `start()` must receive the union of watchlist and position tickers.

#### M6. No `uv.lock`
PLAN §3, §4 and §11 expect a reproducible lockfile. None is committed, and `pyproject.toml` has only lower bounds, so a fresh install takes the newest releases. Because `massive>=1.0.0` is unpinned, SDK behaviour can change underneath the client. Only 2.12.0 was checked here.

**Fix:** run `uv lock`, commit the file, and use `uv sync --frozen` in Docker.

### Low

| # | Location | Issue | Suggestion |
|---|---|---|---|
| L1 | `simulator.py:152`, `massive_client.py:34` | Calling `start()` twice orphans the first task, which survives `stop()` (reproduced). The interface says "call once" but nothing enforces it. | Raise if a task already exists. |
| L2 | `cache.py:19` | `NaN`, zero and negative prices are accepted. `NaN` would also make `json.dumps` emit invalid JSON, breaking parsing of the whole SSE event. | Reject values that are not finite and positive. |
| L3 | `massive_client.py:44` | `start()` waits for the first poll. A slow API or SDK retries would delay app startup (from code reading, not timed). A bad key only produces a log line, while the SSE connection still looks healthy. | Poll inside the background task; consider exposing the last-poll status in `/api/health`. |
| L4 | `stream.py:57` | Nothing is sent while the cache is unchanged (15 s between Massive polls, indefinitely if polls fail). A proxy may close an idle connection. | Send a `: keepalive` comment periodically. |
| L5 | `simulator.py:79`, `cache.py:26` | Rounding to cents makes many ticks look unchanged: about 32 % for AAPL at $190, 36 % for JPM, 71 % for a $50 unknown ticker, 5 % for NVDA. This follows from the specified `dt`. | No code bug. The frontend should flash only on `up`/`down`. Raise `dt` if the demo looks static. |
| L6 | `tests/market/` | `test_events_fire_with_probability_one` has a redundant `0.0 < abs(...)` clause. `test_prices_update` and the loop tests depend on short real sleeps (stable in 20 runs). | Minor cleanup. |
| L7 | `pyproject.toml`, tests | Format drift and the pytest-asyncio warning (§2). | Run `ruff format`; set `asyncio_default_fixture_loop_scope = "function"`. |

---

## 4. What is done well

- **Clean boundaries.** One interface, two sources, one cache, and consumers that don't know which source is active.
- **GBM is correct.** Tests check a deterministic single step, estimated volatility against sigma, and pairwise correlation.
- **The correlation matrix holds up.** Cholesky succeeded with 310 mixed known and unknown tickers.
- **Performance is not a concern.** `step()` takes about 11 µs for 10 tickers.
- **Safe value objects and cache.** `PriceUpdate` is frozen, `get_all()` returns a copy, and writes are locked and covered by a threaded test.
- **Resilient loops.** Both sources survive exceptions and keep the last known prices.
- **SSE basics work end to end.** Under real uvicorn it sent the right content type, the `retry` directive, an immediate full snapshot and updates about every 500 ms.
- **No shared router state.** Each `create_stream_router()` call builds its own router.

## 5. Test gaps

1. A contract test against real SDK models and the real request path (C1–C3).
2. Remove during an in-flight poll (M1).
3. SSE after the cache becomes empty (M2).
4. Invalid tickers and invalid prices (M4, L2).
5. A real-server SSE test that includes shutdown with a connected client (H1). The current tests call the generator directly with a fake request.

## 6. Contract notes for downstream agents

The code has settled these points, but `PLAN.md` does not record them yet (§13 #2). Add them to `PLAN.md` or an `API.md`:

- Unnamed (`message`) events, **one aggregate event per cache change**, shaped as `{ "<TICKER>": {...} }`.
- Fields: `ticker`, `price`, `previous_price`, `timestamp`, `change`, `change_percent`, `direction` (`up` / `down` / `flat`).
- `timestamp` is **Unix epoch seconds as a float**, not milliseconds or ISO. In JavaScript use `new Date(timestamp * 1000)`.
- A full snapshot is sent on connect if the cache is not empty.

## 7. Status of the previous review's findings

| Previous finding | Status now |
|---|---|
| 3.1 Missing hatch wheel packages | Fixed |
| 3.2 Massive tests fail without `massive` | Those failures are gone, but the fake-module approach hides C1 and C2 |
| 3.3 `_generate_events` return type | Fixed |
| 3.4 `version` read without lock | Fixed |
| 3.5 Access to private `_tickers` | Fixed (`GBMSimulator.get_tickers()`) |
| 3.6 Module-level router | Fixed |
| 3.7 Unused imports in tests | Fixed |
| 4.2 Missing SSE, thread-safety and 10-ticker tests | Added (SSE without a real server) |
| 4.3 Unused `DEFAULT_CORR` | Fixed |

## 8. Recommended order of work

1. **C1, C2, C3** in one change, plus the doc corrections. Until then, leave `MASSIVE_API_KEY` empty. If Massive becomes a stretch goal (PLAN §13, simplifications), record that Massive does not currently work.
2. **M1, M2** (small fixes, with tests).
3. **M3, M4** after the PLAN §13 #9 and #10 decisions, before the API and frontend depend on the current shape.
4. **M6** and **H1** before the Dockerfile is written.
5. **M5** with the persistence work, then the low-priority items as convenient.
