"""SQLite connection management, schema initialisation and seed data."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_USER_ID = "default"
DEFAULT_CASH = 10000.0
DEFAULT_TICKERS = ("AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX")

DB_PATH_ENV = "DB_PATH"
BUSY_TIMEOUT_MS = 5000

_SCHEMA_FILE = Path(__file__).with_name("schema.sql")
# backend/app/db/database.py -> parents[3] is the repository root.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string (sortable, timezone-aware)."""
    return datetime.now(UTC).isoformat()


def default_db_path() -> Path:
    """DB path from the DB_PATH env var, else <project root>/db/finally.db."""
    env = os.environ.get(DB_PATH_ENV, "").strip()
    return Path(env) if env else _PROJECT_ROOT / "db" / "finally.db"


class Database:
    """Handle to one SQLite file. Each context manager opens its own short-lived connection,
    so a Database may be shared freely across threads and requests."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        # isolation_level=None: autocommit; transactions are started explicitly.
        conn = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Autocommit connection: each statement commits on its own. Use for reads."""
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """BEGIN IMMEDIATE transaction: takes the write lock up front, so a read-modify-write
        (e.g. cash + position + trade) cannot interleave with another writer.
        Commits on normal exit, rolls back on any exception (which is re-raised)."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        finally:
            conn.close()


def init_db(path: str | Path | None = None) -> Database:
    """Create the database file, schema and seed data if missing. Idempotent.

    Seeding happens only when the default user row is first created, so later user changes
    (e.g. emptying the watchlist) are not undone on restart.
    """
    db_path = Path(path) if path is not None else default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)

    with db.connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(_SCHEMA_FILE.read_text(encoding="utf-8"))

    with db.transaction() as conn:
        now = now_iso()
        created = conn.execute(
            "INSERT OR IGNORE INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
            (DEFAULT_USER_ID, DEFAULT_CASH, now),
        ).rowcount
        if created:
            conn.executemany(
                "INSERT OR IGNORE INTO watchlist (user_id, ticker, added_at) VALUES (?, ?, ?)",
                [(DEFAULT_USER_ID, ticker, now) for ticker in DEFAULT_TICKERS],
            )
    return db
