"""Query layer. Every function takes an open connection first (from Database.connection()
or Database.transaction()) so calls compose inside one transaction.

No business rules here: tickers are stored as given (normalise them first), quantities and
prices are not validated, and P&L math lives in the services.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from .database import DEFAULT_USER_ID, now_iso
from .models import ChatMessage, Position, Snapshot, Trade, WatchlistEntry


class DuplicateTickerError(Exception):
    """The ticker is already on the user's watchlist."""

    def __init__(self, ticker: str) -> None:
        super().__init__(f"{ticker} is already on the watchlist")
        self.ticker = ticker


class UserNotFoundError(LookupError):
    """No users_profile row for the given user_id."""


def _new_id() -> str:
    return str(uuid.uuid4())


# --- cash -------------------------------------------------------------------------------


def get_cash(conn: sqlite3.Connection, *, user_id: str = DEFAULT_USER_ID) -> float:
    row = conn.execute("SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise UserNotFoundError(user_id)
    return float(row["cash_balance"])


def set_cash(conn: sqlite3.Connection, cash: float, *, user_id: str = DEFAULT_USER_ID) -> None:
    cur = conn.execute("UPDATE users_profile SET cash_balance = ? WHERE id = ?", (cash, user_id))
    if cur.rowcount == 0:
        raise UserNotFoundError(user_id)


# --- positions --------------------------------------------------------------------------


def _position(row: sqlite3.Row) -> Position:
    return Position(row["ticker"], row["quantity"], row["avg_cost"], row["updated_at"])


def list_positions(conn: sqlite3.Connection, *, user_id: str = DEFAULT_USER_ID) -> list[Position]:
    rows = conn.execute(
        "SELECT ticker, quantity, avg_cost, updated_at FROM positions"
        " WHERE user_id = ? ORDER BY ticker",
        (user_id,),
    ).fetchall()
    return [_position(r) for r in rows]


def get_position(
    conn: sqlite3.Connection, ticker: str, *, user_id: str = DEFAULT_USER_ID
) -> Position | None:
    row = conn.execute(
        "SELECT ticker, quantity, avg_cost, updated_at FROM positions"
        " WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    ).fetchone()
    return _position(row) if row else None


def upsert_position(
    conn: sqlite3.Connection,
    ticker: str,
    quantity: float,
    avg_cost: float,
    *,
    user_id: str = DEFAULT_USER_ID,
) -> Position:
    now = now_iso()
    conn.execute(
        "INSERT INTO positions (user_id, ticker, quantity, avg_cost, updated_at)"
        " VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT (user_id, ticker) DO UPDATE SET"
        " quantity = excluded.quantity, avg_cost = excluded.avg_cost,"
        " updated_at = excluded.updated_at",
        (user_id, ticker, quantity, avg_cost, now),
    )
    return Position(ticker, quantity, avg_cost, now)


def delete_position(
    conn: sqlite3.Connection, ticker: str, *, user_id: str = DEFAULT_USER_ID
) -> bool:
    cur = conn.execute("DELETE FROM positions WHERE user_id = ? AND ticker = ?", (user_id, ticker))
    return cur.rowcount > 0


# --- trades -----------------------------------------------------------------------------


def insert_trade(
    conn: sqlite3.Connection,
    ticker: str,
    side: str,
    quantity: float,
    price: float,
    *,
    user_id: str = DEFAULT_USER_ID,
) -> Trade:
    trade = Trade(_new_id(), ticker, side, quantity, price, now_iso())
    conn.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (trade.id, user_id, ticker, side, quantity, price, trade.executed_at),
    )
    return trade


def list_trades(
    conn: sqlite3.Connection, limit: int | None = None, *, user_id: str = DEFAULT_USER_ID
) -> list[Trade]:
    """Newest first."""
    rows = conn.execute(
        "SELECT id, ticker, side, quantity, price, executed_at FROM trades"
        " WHERE user_id = ? ORDER BY executed_at DESC, rowid DESC LIMIT ?",
        (user_id, -1 if limit is None else limit),
    ).fetchall()
    return [
        Trade(r["id"], r["ticker"], r["side"], r["quantity"], r["price"], r["executed_at"])
        for r in rows
    ]


# --- watchlist --------------------------------------------------------------------------


def get_watchlist(
    conn: sqlite3.Connection, *, user_id: str = DEFAULT_USER_ID
) -> list[WatchlistEntry]:
    """Oldest added first."""
    rows = conn.execute(
        "SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at, rowid",
        (user_id,),
    ).fetchall()
    return [WatchlistEntry(r["ticker"], r["added_at"]) for r in rows]


def add_watchlist(
    conn: sqlite3.Connection, ticker: str, *, user_id: str = DEFAULT_USER_ID
) -> WatchlistEntry:
    """Raises DuplicateTickerError if the ticker is already watched."""
    now = now_iso()
    cur = conn.execute(
        "INSERT INTO watchlist (user_id, ticker, added_at) VALUES (?, ?, ?)"
        " ON CONFLICT (user_id, ticker) DO NOTHING",
        (user_id, ticker, now),
    )
    if cur.rowcount == 0:
        raise DuplicateTickerError(ticker)
    return WatchlistEntry(ticker, now)


def remove_watchlist(
    conn: sqlite3.Connection, ticker: str, *, user_id: str = DEFAULT_USER_ID
) -> bool:
    cur = conn.execute("DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, ticker))
    return cur.rowcount > 0


# --- portfolio snapshots ----------------------------------------------------------------


def insert_snapshot(
    conn: sqlite3.Connection, total_value: float, *, user_id: str = DEFAULT_USER_ID
) -> Snapshot:
    snap = Snapshot(_new_id(), total_value, now_iso())
    conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)"
        " VALUES (?, ?, ?, ?)",
        (snap.id, user_id, total_value, snap.recorded_at),
    )
    return snap


def list_snapshots(
    conn: sqlite3.Connection, limit: int | None = None, *, user_id: str = DEFAULT_USER_ID
) -> list[Snapshot]:
    """Chronological. With a limit, the most recent `limit` snapshots (still chronological)."""
    rows = conn.execute(
        "SELECT id, total_value, recorded_at FROM portfolio_snapshots"
        " WHERE user_id = ? ORDER BY recorded_at DESC, rowid DESC LIMIT ?",
        (user_id, -1 if limit is None else limit),
    ).fetchall()
    return [Snapshot(r["id"], r["total_value"], r["recorded_at"]) for r in reversed(rows)]


# --- chat -------------------------------------------------------------------------------


def insert_chat_message(
    conn: sqlite3.Connection,
    role: str,
    content: str,
    actions: Any | None = None,
    *,
    user_id: str = DEFAULT_USER_ID,
) -> ChatMessage:
    """`actions` is any JSON-serialisable object (stored as JSON text); None stores NULL."""
    msg = ChatMessage(_new_id(), role, content, actions, now_iso())
    conn.execute(
        "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            msg.id,
            user_id,
            role,
            content,
            None if actions is None else json.dumps(actions),
            msg.created_at,
        ),
    )
    return msg


def list_chat_messages(
    conn: sqlite3.Connection, limit: int | None = None, *, user_id: str = DEFAULT_USER_ID
) -> list[ChatMessage]:
    """Chronological. With a limit, the most recent `limit` messages (still chronological)."""
    rows = conn.execute(
        "SELECT id, role, content, actions, created_at FROM chat_messages"
        " WHERE user_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?",
        (user_id, -1 if limit is None else limit),
    ).fetchall()
    return [
        ChatMessage(
            r["id"],
            r["role"],
            r["content"],
            None if r["actions"] is None else json.loads(r["actions"]),
            r["created_at"],
        )
        for r in reversed(rows)
    ]
