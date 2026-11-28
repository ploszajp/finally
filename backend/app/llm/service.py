"""Chat flow (planning/API_CHAT.md "Processing a chat message").

store user message -> build prompt -> LLM (or mock) -> watchlist changes, then trades ->
store assistant message with per-action results -> return both messages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import weakref
from dataclasses import asdict
from typing import Any

from app.db import ChatMessage
from app.db import repository as repo
from app.market import InvalidTickerError, normalize_ticker
from app.services import portfolio as portfolio_service
from app.services import trading
from app.services import watchlist as watchlist_service
from app.services.errors import TradeError, WatchlistError
from app.services.state import get_state

from .client import call_llm
from .errors import LLMError
from .mock import is_mock_mode, mock_reply
from .schema import LLMResponse, TradeAction, WatchlistAction

logger = logging.getLogger(__name__)

HISTORY_WINDOW = 20
DEFAULT_HISTORY_LIMIT = 50
MAX_HISTORY_LIMIT = 200
MAX_MESSAGE_LENGTH = 2000

SYSTEM_PROMPT = """\
You are FinAlly, an AI trading assistant inside a simulated trading workstation. \
The money is virtual; trades execute instantly as market orders at the current price, \
with no fees and no confirmation step.

Your job:
- Analyze the user's portfolio: composition, concentration risk, unrealized P&L.
- Suggest trades with brief, data-driven reasoning.
- Execute trades when the user asks for them or agrees to your suggestion, by listing them \
in "trades". Never trade without the user's request or consent.
- Manage the watchlist when asked (or when it clearly helps), via "watchlist_changes".
- A ticker can only be traded once it has a price; to trade a ticker that is not on the \
watchlist, add it in the same reply (watchlist changes run before trades).
- Be concise. Use numbers from the portfolio context; never invent prices.

The current portfolio state is given as JSON in a separate system message. Messages \
starting with "[actions]" report what actually happened to your earlier requested actions; \
if something was rejected, say so when relevant.

Always reply with JSON matching the schema: "message" (text shown to the user), "trades" \
(list of {ticker, side: "buy"|"sell", quantity > 0}) and "watchlist_changes" (list of \
{ticker, action: "add"|"remove"}). Use empty lists when there is nothing to do."""

_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    weakref.WeakKeyDictionary()
)


def _chat_lock() -> asyncio.Lock:
    """One chat at a time (per event loop, i.e. per server process)."""
    loop = asyncio.get_running_loop()
    lock = _locks.get(loop)
    if lock is None:
        lock = _locks[loop] = asyncio.Lock()
    return lock


# --- serialisation ----------------------------------------------------------------------


def message_to_dict(msg: ChatMessage) -> dict:
    return asdict(msg)


def empty_actions(error: str | None = None) -> dict:
    return {"watchlist_changes": [], "trades": [], "error": error}


# --- prompt -----------------------------------------------------------------------------


def build_portfolio_context() -> dict:
    """Cash, total value, positions and watchlist with live prices (None when unknown)."""
    portfolio = portfolio_service.get_portfolio()
    watchlist = watchlist_service.get_watchlist()
    return {
        "cash_balance": portfolio["cash_balance"],
        "total_value": portfolio["total_value"],
        "positions_value": portfolio["positions_value"],
        "unrealized_pnl": portfolio["unrealized_pnl"],
        "positions": [
            {
                "ticker": p["ticker"],
                "quantity": p["quantity"],
                "avg_cost": p["avg_cost"],
                "current_price": p["current_price"],
                "unrealized_pnl": p["unrealized_pnl"],
                "pnl_percent": p["pnl_percent"],
                "weight_percent": p.get("weight_percent"),
            }
            for p in portfolio["positions"]
        ],
        "watchlist": [
            {
                "ticker": w["ticker"],
                "price": w["price"],
                "day_change_percent": w["day_change_percent"],
            }
            for w in watchlist
        ],
    }


def _fmt_qty(value: Any) -> str:
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def summarize_actions(actions: dict | None) -> str | None:
    """Compact text of earlier action results, e.g. "[actions] buy 5 AAPL: executed @ 191.23"."""
    if not actions:
        return None
    parts: list[str] = []
    for c in actions.get("watchlist_changes") or []:
        part = f"{c.get('action')} {c.get('ticker')} (watchlist): {c.get('status')}"
        if c.get("error"):
            part += f" ({c['error']})"
        parts.append(part)
    for t in actions.get("trades") or []:
        part = f"{t.get('side')} {_fmt_qty(t.get('quantity'))} {t.get('ticker')}: {t.get('status')}"
        if t.get("status") == "executed" and t.get("price") is not None:
            part += f" @ {t['price']}"
        if t.get("error"):
            part += f" ({t['error']})"
        parts.append(part)
    return "[actions] " + "; ".join(parts) if parts else None


def build_messages(history: list[ChatMessage], context: dict, user_message: str) -> list[dict]:
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": "Current portfolio (JSON):\n" + json.dumps(context, separators=(",", ":")),
        },
    ]
    for msg in history:
        if msg.role == "user":
            messages.append({"role": "user", "content": msg.content})
        elif msg.role == "assistant":
            if isinstance(msg.actions, dict) and msg.actions.get("error"):
                continue  # failed LLM calls are not sent back as history
            messages.append({"role": "assistant", "content": msg.content})
            summary = summarize_actions(msg.actions if isinstance(msg.actions, dict) else None)
            if summary:
                messages.append({"role": "system", "content": summary})
    messages.append({"role": "user", "content": user_message})
    return messages


# --- actions ----------------------------------------------------------------------------


def _display_ticker(raw: str) -> str:
    try:
        return normalize_ticker(raw)
    except InvalidTickerError:
        return raw


async def _run_watchlist_change(change: WatchlistAction) -> dict:
    result = {
        "ticker": _display_ticker(change.ticker),
        "action": change.action,
        "status": "executed",
        "error": None,
    }
    try:
        if change.action == "add":
            await watchlist_service.add_to_watchlist(change.ticker)
        else:
            await watchlist_service.remove_from_watchlist(change.ticker)
    except (InvalidTickerError, WatchlistError) as e:
        result.update(status="rejected", error=str(e))
    except Exception:
        logger.exception("Watchlist change from chat failed unexpectedly")
        result.update(status="rejected", error="Internal error while changing the watchlist")
    return result


async def _run_trade(trade: TradeAction) -> dict:
    result: dict[str, Any] = {
        "ticker": _display_ticker(trade.ticker),
        "side": trade.side,
        "quantity": trade.quantity,
        "status": "executed",
        "price": None,
        "error": None,
    }
    try:
        executed = await trading.execute_trade(trade.ticker, trade.side, trade.quantity)
        result["price"] = executed["trade"]["price"]
        result["quantity"] = executed["trade"]["quantity"]
    except (InvalidTickerError, TradeError) as e:
        result.update(status="rejected", error=str(e))
    except Exception:
        logger.exception("Trade from chat failed unexpectedly")
        result.update(status="rejected", error="Internal error while executing the trade")
    return result


async def execute_actions(reply: LLMResponse) -> dict:
    """All watchlist changes first, then all trades, each independently (in listed order)."""
    changes = [await _run_watchlist_change(c) for c in reply.watchlist_changes]
    trades = [await _run_trade(t) for t in reply.trades]
    return {"watchlist_changes": changes, "trades": trades, "error": None}


# --- persistence ------------------------------------------------------------------------


def _insert(role: str, content: str, actions: dict | None) -> ChatMessage:
    with get_state().db.connection() as conn:
        return repo.insert_chat_message(conn, role, content, actions)


def _recent(limit: int) -> list[ChatMessage]:
    with get_state().db.connection() as conn:
        return repo.list_chat_messages(conn, limit)


def get_history(limit: int = DEFAULT_HISTORY_LIMIT) -> dict:
    limit = max(1, min(limit, MAX_HISTORY_LIMIT))
    return {"messages": [message_to_dict(m) for m in _recent(limit)]}


# --- flow -------------------------------------------------------------------------------


async def _get_reply(messages: list[dict], user_message: str) -> LLMResponse:
    if is_mock_mode():
        return mock_reply(user_message)
    return await call_llm(messages)


async def process_chat(message: str) -> dict:
    """Handle one chat message. Returns {"user_message": ..., "assistant_message": ...}.

    LLM failures never raise: they become an assistant message with actions.error set.
    """
    text = message.strip()
    async with _chat_lock():
        # History first (it must not include the new message), then store the new message.
        history = await asyncio.to_thread(_recent, HISTORY_WINDOW)
        user_msg = await asyncio.to_thread(_insert, "user", text, None)

        try:
            context = await asyncio.to_thread(build_portfolio_context)
            prompt = build_messages(history, context, text)
            reply = await _get_reply(prompt, text)
        except LLMError as e:
            content, actions = e.user_message, empty_actions(e.code)
        else:
            content = reply.message
            actions = await execute_actions(reply)

        assistant_msg = await asyncio.to_thread(_insert, "assistant", content, actions)
    return {
        "user_message": message_to_dict(user_msg),
        "assistant_message": message_to_dict(assistant_msg),
    }
