# Chat API and LLM behaviour

Owned by the LLM engineer. This is the chat section of the API contract (`planning/API.md` covers everything else and uses the same error format). It resolves PLAN.md §13 items 4, 5 and 6.

All bodies are JSON. Timestamps are ISO 8601 UTC strings (e.g. `"2026-11-28T10:15:30.123456+00:00"`). Errors that are not LLM failures use the shared format `{"detail": "..."}`.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send a message; the reply comes back complete (no streaming) |
| GET | `/api/chat/history` | Stored conversation, oldest first, to restore the panel after a reload |

### The `ChatMessage` object

Both endpoints return messages in this shape.

```json
{
  "id": "6f1c2a9e-...",
  "role": "assistant",
  "content": "Bought 5 AAPL. You now hold 15 shares.",
  "actions": {
    "watchlist_changes": [
      {"ticker": "PYPL", "action": "add", "status": "executed", "error": null}
    ],
    "trades": [
      {"ticker": "AAPL", "side": "buy", "quantity": 5, "status": "executed", "price": 191.23, "error": null},
      {"ticker": "TSLA", "side": "buy", "quantity": 1000, "status": "rejected", "price": null, "error": "Insufficient cash: need $250,000.00, have $9,043.85"}
    ],
    "error": null
  },
  "created_at": "2026-11-28T10:15:31.002000+00:00"
}
```

| Field | Meaning |
|---|---|
| `role` | `"user"` or `"assistant"` |
| `content` | Text to show. For a failed LLM call it is a friendly error text (see below) |
| `actions` | `null` for user messages. Always an object for assistant messages, with all three keys present |
| `actions.watchlist_changes[]` | Result of each requested watchlist change, in execution order |
| `actions.trades[]` | Result of each requested trade, in execution order |
| `.status` | `"executed"` or `"rejected"` |
| `.error` | `null` when executed, otherwise the human-readable reason (the same text the REST endpoint puts in `detail`) |
| `trades[].price` | Fill price when executed, `null` when rejected |
| `ticker` | Normalised (upper-case) when valid; as the LLM sent it when the format was invalid |
| `actions.error` | `null` on success, otherwise an error code (see "LLM failures"). When set, both arrays are empty |

The frontend shows each action inline under the assistant message: executed ones as confirmations, rejected ones clearly marked with their `error`. The assistant `content` is written by the LLM *before* the actions run, so it can claim a trade that was then rejected; the inline status is the source of truth. After any chat reply the frontend should refresh portfolio and watchlist (or do it only when some action has `status: "executed"`).

### POST /api/chat

Request:

```json
{"message": "Buy 5 AAPL and add PYPL to my watchlist"}
```

- `message`: string, trimmed, 1 to 2000 characters. Empty/whitespace-only, too long, or missing → **422** (FastAPI validation, `{"detail": [...]}`).

Response **200**, always, when the request is valid, including when the LLM fails:

```json
{
  "user_message": { "id": "...", "role": "user", "content": "Buy 5 AAPL and add PYPL to my watchlist", "actions": null, "created_at": "..." },
  "assistant_message": { "id": "...", "role": "assistant", "content": "...", "actions": { "watchlist_changes": [...], "trades": [...], "error": null }, "created_at": "..." }
}
```

Both messages are already stored when the response arrives. The frontend appends both to the panel (or replaces its optimistic copy of the user message with `user_message`).

Requests are handled one at a time on the server (a lock around the chat flow), so two quick messages cannot interleave their actions. The frontend should disable the send button while a request is in flight anyway.

### GET /api/chat/history

Query: `limit` (optional int, default 50, 1 to 200; out of range → 422).

Response **200**:

```json
{"messages": [ChatMessage, ...]}
```

The most recent `limit` messages, ordered oldest first. Empty database → `{"messages": []}`. Assistant messages that hold an LLM error are included, so the user sees what happened.

## Processing a chat message

1. Validate and store the user message (it is stored even if the LLM then fails).
2. Build the prompt: system prompt, current portfolio context, the last **20** stored messages before the new one (assistant messages with `actions.error` set are skipped), then the new user message.
3. Call the LLM (or the mock, see below), requesting structured output.
4. Execute the requested actions: **all watchlist changes first, then all trades**, each in the order the LLM listed them. Every action runs independently: a rejected one does not stop the rest.
5. Store the assistant message with the per-action results in `chat_messages.actions` (the same JSON as `actions` above).
6. Return both messages.

Watchlist changes and trades go through exactly the same service functions as the REST endpoints, so validation, ticker normalisation, error texts, price tracking and portfolio snapshots behave identically. A watchlist add of a ticker that is already watched, or a remove of one that is not, is `rejected` with the service's message (the REST equivalents are 409 and 404).

### Portfolio context sent to the LLM

A JSON block in a second system message: cash balance, total portfolio value, positions (ticker, quantity, avg cost, current price, unrealized P&L, P&L %), and the watchlist with current price and daily change %. Prices that are not yet available are `null`.

In the conversation history, each earlier assistant message is followed by a compact summary of its action results (e.g. `[actions] buy 1000 TSLA: rejected (Insufficient cash ...)`), so the LLM can tell the user what failed on the next turn.

## Structured output schema (§13.5)

Strict structured outputs require every field to be required, so all three are always present; unused arrays are empty.

```json
{
  "message": "string",
  "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],
  "watchlist_changes": [{"ticker": "PYPL", "action": "add"}]
}
```

- `side` is `"buy"` or `"sell"`; `action` is `"add"` or `"remove"`; `quantity` is a number (fractional allowed; the trade service validates `> 0` and rounding).
- No other fields are allowed (`additionalProperties: false`).

Model call: LiteLLM → OpenRouter, model `openrouter/openai/gpt-oss-120b`, provider order `["cerebras"]`, `reasoning_effort="low"`, `response_format` = the pydantic schema, timeout 30 s.

## LLM failures (§13.6)

The app starts without `OPENROUTER_API_KEY`; only the chat is affected. On any LLM failure `POST /api/chat` still returns **200**. The user message is stored, and the assistant message is stored with no actions, `actions.error` set to a code, and a friendly `content`:

| `actions.error` | When | `content` |
|---|---|---|
| `llm_not_configured` | `LLM_MOCK` is not `true` and `OPENROUTER_API_KEY` is missing or empty | `The AI assistant is not configured. Set OPENROUTER_API_KEY in .env and restart the app. Trading and the watchlist still work.` |
| `llm_timeout` | No reply within 30 s | `The AI assistant took too long to respond. Please try again.` |
| `llm_unavailable` | Network error, auth error, rate limit, provider error | `The AI assistant is unavailable right now. Please try again in a moment.` |
| `llm_invalid_response` | The reply is not valid JSON for the schema, after one retry | `The AI assistant returned a response I could not understand. Please try rephrasing.` |

The frontend may style a message with `actions.error != null` as an error. Error messages are not sent back to the LLM as history. The API key and raw provider errors are never returned to the client or logged in full.

## Mock mode (§13.4)

With `LLM_MOCK=true` the LLM is never called and no API key is needed. The reply is a pure function of the user message, so tests can assert on exact values. Matching is case-insensitive on the trimmed message.

Rules, all evaluated (several can apply to one message):

| Rule | Pattern (regex, case-insensitive) | Produces |
|---|---|---|
| Error | contains `mock error` | Stops here: an `llm_unavailable` failure exactly as in the table above (no actions) |
| Add | `\badd\s+([A-Za-z][A-Za-z.\-]{0,9})\b` | `watchlist_changes`: `{"ticker": <captured word, upper-cased>, "action": "add"}`, first match only |
| Remove | `\bremove\s+([A-Za-z][A-Za-z.\-]{0,9})\b` | `watchlist_changes`: `{"ticker": <captured, upper-cased>, "action": "remove"}`, first match only |
| Buy | `\bbuy\b` | `trades`: `{"ticker": "AAPL", "side": "buy", "quantity": 1}` |
| Sell | `\bsell\b` | `trades`: `{"ticker": "AAPL", "side": "sell", "quantity": 1}` |

Order within the arrays: add before remove; buy before sell. They then execute through the normal path (watchlist first, then trades), so results, rejections and persistence are real.

Mock `content`:

- No rule matched: `Hello from FinAlly (mock mode). I can buy or sell AAPL and add or remove watchlist tickers.`
- At least one action produced: `Mock mode: processing your request.` followed by one sentence per action, in order, joined by spaces:
  - `Adding <T> to your watchlist.` / `Removing <T> from your watchlist.`
  - `Buying 1 share of AAPL.` / `Selling 1 share of AAPL.`

Examples:

| Message | content | actions |
|---|---|---|
| `hello` | `Hello from FinAlly (mock mode). I can buy or sell AAPL and add or remove watchlist tickers.` | both arrays empty |
| `Buy some apple` | `Mock mode: processing your request. Buying 1 share of AAPL.` | trades: buy 1 AAPL |
| `add PYPL` | `Mock mode: processing your request. Adding PYPL to your watchlist.` | watchlist_changes: add PYPL |
| `remove nflx and sell` | `Mock mode: processing your request. Removing NFLX from your watchlist. Selling 1 share of AAPL.` | remove NFLX; sell 1 AAPL |
| `sell` (no AAPL held) | `Mock mode: processing your request. Selling 1 share of AAPL.` | trades: sell 1 AAPL, `status: "rejected"`, `error` from the trade service |
| `mock error` | `The AI assistant is unavailable right now. Please try again in a moment.` | `error: "llm_unavailable"` |

Note that `add` captures the next word whatever it is (`add some` → ticker `SOME`, which the simulator will happily price). Tests should use real-looking tickers.
