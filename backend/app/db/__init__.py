"""Database layer: SQLite connection management, schema/seed initialisation and queries.

from app.db import init_db, repository as repo

db = init_db()                      # once at startup; DB_PATH env or <root>/db/finally.db
with db.connection() as conn:       # autocommit reads
    cash = repo.get_cash(conn)
with db.transaction() as conn:      # BEGIN IMMEDIATE read-modify-write
    repo.set_cash(conn, cash - 100)
"""

from . import repository
from .database import (
    DB_PATH_ENV,
    DEFAULT_CASH,
    DEFAULT_TICKERS,
    DEFAULT_USER_ID,
    Database,
    default_db_path,
    init_db,
    now_iso,
)
from .models import ChatMessage, Position, Snapshot, Trade, WatchlistEntry
from .repository import DuplicateTickerError, UserNotFoundError

__all__ = [
    "DB_PATH_ENV",
    "DEFAULT_CASH",
    "DEFAULT_TICKERS",
    "DEFAULT_USER_ID",
    "ChatMessage",
    "Database",
    "DuplicateTickerError",
    "Position",
    "Snapshot",
    "Trade",
    "UserNotFoundError",
    "WatchlistEntry",
    "default_db_path",
    "init_db",
    "now_iso",
    "repository",
]
