import sqlite3
import threading

import pytest

from app.db import (
    DB_PATH_ENV,
    DEFAULT_CASH,
    DEFAULT_TICKERS,
    default_db_path,
    init_db,
)
from app.db import repository as repo

TABLES = {
    "users_profile",
    "watchlist",
    "positions",
    "trades",
    "portfolio_snapshots",
    "chat_messages",
}


def test_init_creates_file_parent_dirs_and_tables(db, db_path):
    assert db_path.exists()
    with db.connection() as conn:
        names = {
            r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert TABLES <= names


def test_seed_defaults(db):
    with db.connection() as conn:
        assert repo.get_cash(conn) == DEFAULT_CASH == 10000.0
        assert [w.ticker for w in repo.get_watchlist(conn)] == list(DEFAULT_TICKERS)
        assert repo.list_positions(conn) == []


def test_init_is_idempotent(db_path):
    init_db(db_path)
    db = init_db(db_path)
    with db.connection() as conn:
        assert len(repo.get_watchlist(conn)) == 10
        assert conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0] == 1


def test_seed_runs_only_once(db, db_path):
    with db.transaction() as conn:
        for entry in repo.get_watchlist(conn):
            repo.remove_watchlist(conn, entry.ticker)
        repo.set_cash(conn, 42.0)
    db2 = init_db(db_path)
    with db2.connection() as conn:
        assert repo.get_watchlist(conn) == []
        assert repo.get_cash(conn) == 42.0


def test_pragmas(db):
    with db.connection() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_default_db_path_env(monkeypatch, tmp_path):
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "x.db"))
    assert default_db_path() == tmp_path / "x.db"
    monkeypatch.delenv(DB_PATH_ENV)
    p = default_db_path()
    assert p.name == "finally.db" and p.parent.name == "db"
    assert (p.parent.parent / "planning").is_dir()  # repository root


def test_init_db_without_path_uses_env(monkeypatch, tmp_path):
    monkeypatch.setenv(DB_PATH_ENV, str(tmp_path / "env.db"))
    db = init_db()
    assert db.path == tmp_path / "env.db"
    assert db.path.exists()


def test_transaction_commits(db):
    with db.transaction() as conn:
        repo.set_cash(conn, 500.0)
    with db.connection() as conn:
        assert repo.get_cash(conn) == 500.0


def test_transaction_rolls_back_on_exception(db):
    with pytest.raises(RuntimeError), db.transaction() as conn:
        repo.set_cash(conn, 1.0)
        repo.upsert_position(conn, "AAPL", 5, 100.0)
        repo.insert_trade(conn, "AAPL", "buy", 5, 100.0)
        raise RuntimeError("boom")
    with db.connection() as conn:
        assert repo.get_cash(conn) == DEFAULT_CASH
        assert repo.list_positions(conn) == []
        assert repo.list_trades(conn) == []


def test_transaction_rolls_back_on_constraint_error(db):
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        repo.set_cash(conn, 1.0)
        repo.insert_trade(conn, "AAPL", "hold", 1, 1.0)  # CHECK fails
    with db.connection() as conn:
        assert repo.get_cash(conn) == DEFAULT_CASH


def test_transaction_serialises_read_modify_write(db):
    """Concurrent BEGIN IMMEDIATE read-modify-writes never lose an update."""
    workers, per_worker = 4, 25
    errors = []

    def work():
        try:
            for _ in range(per_worker):
                with db.transaction() as conn:
                    repo.set_cash(conn, repo.get_cash(conn) - 1)
        except sqlite3.Error as exc:
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    with db.connection() as conn:
        assert repo.get_cash(conn) == DEFAULT_CASH - workers * per_worker


def test_database_shared_across_threads(db):
    result = []

    def read():
        with db.connection() as conn:
            result.append(repo.get_cash(conn))

    t = threading.Thread(target=read)
    t.start()
    t.join()
    assert result == [DEFAULT_CASH]


def test_foreign_key_rejects_unknown_user(db):
    with db.connection() as conn, pytest.raises(sqlite3.IntegrityError):
        repo.add_watchlist(conn, "AAPL", user_id="nobody")
