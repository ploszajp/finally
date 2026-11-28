"""Trade logic edge cases, called through the service functions (as the chat service does)."""

from __future__ import annotations

import asyncio

import pytest

from app.market import InvalidTickerError
from app.services import portfolio, trading
from app.services.errors import TradeError


def run(coro):
    return asyncio.run(coro)


def test_weighted_avg_cost_and_partial_sell_keeps_avg(client, source):
    source.set_price("AAPL", 100.0)
    run(trading.execute_trade("AAPL", "buy", 10))
    source.set_price("AAPL", 130.0)
    run(trading.execute_trade("AAPL", "buy", 5))
    pos = portfolio.get_portfolio()["positions"][0]
    assert pos["quantity"] == 15.0
    assert pos["avg_cost"] == 110.0

    result = run(trading.execute_trade("AAPL", "sell", 5))
    pos = result["portfolio"]["positions"][0]
    assert pos["quantity"] == 10.0
    assert pos["avg_cost"] == 110.0
    # 10000 - 1000 - 650 + 650
    assert result["portfolio"]["cash_balance"] == 9000.0


def test_sell_at_loss(client, source):
    source.set_price("TSLA", 200.0)
    run(trading.execute_trade("TSLA", "buy", 10))
    source.set_price("TSLA", 150.0)
    result = run(trading.execute_trade("TSLA", "sell", 10))
    assert result["portfolio"]["positions"] == []
    assert result["portfolio"]["cash_balance"] == 9500.0


def test_full_sell_deletes_position_with_fractional_qty(client, source):
    source.set_price("NVDA", 123.45)
    run(trading.execute_trade("NVDA", "buy", 0.3333))
    result = run(trading.execute_trade("NVDA", "sell", 0.3333))
    assert result["portfolio"]["positions"] == []
    assert result["trade"]["total"] == 41.15  # 0.3333 * 123.45 = 41.146...
    assert result["portfolio"]["cash_balance"] == 10000.0


def test_quantity_rounded_to_4_decimals(client, source):
    result = run(trading.execute_trade("AAPL", "buy", 1.234567))
    assert result["trade"]["quantity"] == 1.2346


def test_buy_exact_cash(client, source):
    source.set_price("AAPL", 1000.0)
    result = run(trading.execute_trade("AAPL", "buy", 10))
    assert result["portfolio"]["cash_balance"] == 0.0
    with pytest.raises(TradeError, match="Insufficient cash"):
        run(trading.execute_trade("AAPL", "buy", 0.001))


def test_oversell_rejected_and_nothing_changes(client, source):
    run(trading.execute_trade("AAPL", "buy", 2))
    with pytest.raises(TradeError, match="trying to sell 3 AAPL, have 2"):
        run(trading.execute_trade("AAPL", "sell", 3))
    p = portfolio.get_portfolio()
    assert p["positions"][0]["quantity"] == 2.0
    assert p["cash_balance"] == 9800.0


def test_invalid_inputs(client, source):
    with pytest.raises(InvalidTickerError):
        run(trading.execute_trade("bad ticker", "buy", 1))
    with pytest.raises(TradeError, match="Invalid side"):
        run(trading.execute_trade("AAPL", "hold", 1))
    with pytest.raises(TradeError, match="greater than 0"):
        run(trading.execute_trade("AAPL", "buy", float("nan")))
    with pytest.raises(TradeError, match="No price available for XYZ"):
        run(trading.execute_trade("xyz", "buy", 1))


def test_concurrent_buys_cannot_overspend(client, source):
    source.set_price("AAPL", 1000.0)

    async def both():
        return await asyncio.gather(
            *(trading.execute_trade("AAPL", "buy", 6) for _ in range(2)),
            return_exceptions=True,
        )

    results = run(both())
    errors = [r for r in results if isinstance(r, Exception)]
    assert len(errors) == 1 and isinstance(errors[0], TradeError)
    assert portfolio.get_portfolio()["cash_balance"] == 4000.0
