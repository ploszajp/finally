"""Portfolio valuation, snapshots and history."""

from __future__ import annotations

import sqlite3

from app.db import repository as repo
from app.market import PriceCache

from .state import get_state

DEFAULT_HISTORY_LIMIT = 1000
MAX_HISTORY_LIMIT = 5000


def _pct(numerator: float, denominator: float) -> float:
    return round(numerator / denominator * 100, 2) if denominator else 0.0


def build_portfolio(conn: sqlite3.Connection, cache: PriceCache) -> dict:
    """Value the portfolio from the database rows and live cached prices (API.md §3)."""
    cash = repo.get_cash(conn)
    rows = []
    positions_value = 0.0
    cost_basis = 0.0
    for p in repo.list_positions(conn):
        price = cache.get_price(p.ticker)
        if price is None:
            price = p.avg_cost  # no live price yet: value at cost so totals stay sane
        market_value = p.quantity * price
        positions_value += market_value
        cost_basis += p.quantity * p.avg_cost
        rows.append(
            {
                "ticker": p.ticker,
                "quantity": round(p.quantity, 4),
                "avg_cost": round(p.avg_cost, 4),
                "current_price": price,
                "market_value": round(market_value, 2),
                "unrealized_pnl": round((price - p.avg_cost) * p.quantity, 2),
                "pnl_percent": _pct(price - p.avg_cost, p.avg_cost),
            }
        )
    total_value = cash + positions_value
    for row in rows:
        row["weight_percent"] = _pct(row["market_value"], total_value)
    unrealized = positions_value - cost_basis
    return {
        "cash_balance": round(cash, 2),
        "positions_value": round(positions_value, 2),
        "total_value": round(total_value, 2),
        "unrealized_pnl": round(unrealized, 2),
        "unrealized_pnl_percent": _pct(unrealized, cost_basis),
        "positions": rows,
    }


def get_portfolio() -> dict:
    state = get_state()
    with state.db.connection() as conn:
        return build_portfolio(conn, state.cache)


def record_snapshot() -> dict:
    """Store the current total portfolio value. Returns the snapshot."""
    state = get_state()
    with state.db.transaction() as conn:
        total = build_portfolio(conn, state.cache)["total_value"]
        snap = repo.insert_snapshot(conn, total)
    return {"total_value": snap.total_value, "recorded_at": snap.recorded_at}


def get_history(limit: int = DEFAULT_HISTORY_LIMIT) -> dict:
    limit = max(1, min(limit, MAX_HISTORY_LIMIT))
    with get_state().db.connection() as conn:
        snaps = repo.list_snapshots(conn, limit)
    return {
        "snapshots": [{"total_value": s.total_value, "recorded_at": s.recorded_at} for s in snaps]
    }
