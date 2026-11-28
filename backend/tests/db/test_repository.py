import sqlite3

import pytest

from app.db import (
    ChatMessage,
    DuplicateTickerError,
    Position,
    UserNotFoundError,
    WatchlistEntry,
)
from app.db import repository as repo


@pytest.fixture
def conn(db):
    with db.connection() as c:
        yield c


# --- cash


def test_set_and_get_cash(conn):
    repo.set_cash(conn, 1234.56)
    assert repo.get_cash(conn) == 1234.56


def test_cash_unknown_user(conn):
    with pytest.raises(UserNotFoundError):
        repo.get_cash(conn, user_id="nobody")
    with pytest.raises(UserNotFoundError):
        repo.set_cash(conn, 1.0, user_id="nobody")


# --- positions


def test_position_crud(conn):
    assert repo.get_position(conn, "AAPL") is None
    created = repo.upsert_position(conn, "AAPL", 10, 190.0)
    assert isinstance(created, Position)
    assert repo.get_position(conn, "AAPL") == created

    updated = repo.upsert_position(conn, "AAPL", 2.5, 185.25)
    got = repo.get_position(conn, "AAPL")
    assert (got.quantity, got.avg_cost) == (2.5, 185.25)
    assert got == updated

    repo.upsert_position(conn, "MSFT", 1, 400.0)
    assert [p.ticker for p in repo.list_positions(conn)] == ["AAPL", "MSFT"]

    assert repo.delete_position(conn, "AAPL") is True
    assert repo.delete_position(conn, "AAPL") is False
    assert [p.ticker for p in repo.list_positions(conn)] == ["MSFT"]


def test_positions_are_per_user(conn):
    conn.execute("INSERT INTO users_profile (id, cash_balance, created_at) VALUES ('u2', 5, 'x')")
    repo.upsert_position(conn, "AAPL", 1, 1.0, user_id="u2")
    assert repo.list_positions(conn) == []
    assert len(repo.list_positions(conn, user_id="u2")) == 1


def test_one_position_row_per_ticker(conn):
    repo.upsert_position(conn, "AAPL", 1, 1.0)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO positions (user_id, ticker, quantity, avg_cost, updated_at)"
            " VALUES ('default', 'AAPL', 1, 1, 'x')"
        )


# --- trades


def test_insert_and_list_trades(conn):
    t1 = repo.insert_trade(conn, "AAPL", "buy", 1.5, 190.0)
    t2 = repo.insert_trade(conn, "AAPL", "sell", 0.5, 195.0)
    assert t1.id != t2.id
    assert repo.list_trades(conn) == [t2, t1]  # newest first
    assert repo.list_trades(conn, limit=1) == [t2]


def test_trade_side_check(conn):
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_trade(conn, "AAPL", "short", 1, 1.0)


# --- watchlist


def test_watchlist_add_remove(conn):
    entry = repo.add_watchlist(conn, "PYPL")
    assert isinstance(entry, WatchlistEntry)
    tickers = [w.ticker for w in repo.get_watchlist(conn)]
    assert tickers[-1] == "PYPL" and len(tickers) == 11

    assert repo.remove_watchlist(conn, "PYPL") is True
    assert repo.remove_watchlist(conn, "PYPL") is False
    assert "PYPL" not in [w.ticker for w in repo.get_watchlist(conn)]


def test_watchlist_duplicate(conn):
    with pytest.raises(DuplicateTickerError) as exc:
        repo.add_watchlist(conn, "AAPL")
    assert exc.value.ticker == "AAPL"
    assert [w.ticker for w in repo.get_watchlist(conn)].count("AAPL") == 1


def test_watchlist_unique_constraint(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO watchlist (user_id, ticker, added_at) VALUES ('default', 'AAPL', 'x')"
        )


def test_duplicate_inside_transaction_keeps_other_work(db):
    with db.transaction() as conn:
        repo.add_watchlist(conn, "PYPL")
        with pytest.raises(DuplicateTickerError):
            repo.add_watchlist(conn, "AAPL")
    with db.connection() as conn:
        assert "PYPL" in [w.ticker for w in repo.get_watchlist(conn)]


# --- snapshots


def test_snapshots(conn):
    snaps = [repo.insert_snapshot(conn, v) for v in (10000.0, 10050.0, 9990.5)]
    assert repo.list_snapshots(conn) == snaps  # chronological
    assert repo.list_snapshots(conn, limit=2) == snaps[1:]  # most recent 2, chronological


def test_snapshots_empty(conn):
    assert repo.list_snapshots(conn) == []


# --- chat


def test_chat_messages_roundtrip(conn):
    actions = {
        "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 1, "status": "executed"}],
        "watchlist_changes": [],
    }
    m1 = repo.insert_chat_message(conn, "user", "buy one apple")
    m2 = repo.insert_chat_message(conn, "assistant", "Done.", actions)
    assert isinstance(m2, ChatMessage)

    msgs = repo.list_chat_messages(conn)
    assert msgs == [m1, m2]
    assert msgs[0].actions is None
    assert msgs[1].actions == actions
    raw = conn.execute("SELECT actions FROM chat_messages WHERE id = ?", (m1.id,)).fetchone()
    assert raw[0] is None


def test_chat_messages_limit_returns_latest_chronological(conn):
    for i in range(5):
        repo.insert_chat_message(conn, "user", f"m{i}")
    assert [m.content for m in repo.list_chat_messages(conn, limit=3)] == ["m2", "m3", "m4"]


def test_chat_role_check(conn):
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_chat_message(conn, "system", "nope")
