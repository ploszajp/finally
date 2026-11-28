"""Business logic shared by the REST routes and the LLM chat service.

Call these functions instead of touching the database or the market source directly:

    from app.services import trading, watchlist, portfolio

    await trading.execute_trade("AAPL", "buy", 10)        # -> {"trade": ..., "portfolio": ...}
    await watchlist.add_to_watchlist("PYPL")              # -> watchlist item
    await watchlist.remove_from_watchlist("PYPL")         # -> {"ticker": ..., "removed": True}
    portfolio.get_portfolio()                             # -> API.md §3 GET shape
    watchlist.get_watchlist()                             # -> list of watchlist items

They use the process-wide AppState (app.services.state), set up by the FastAPI lifespan.
Errors: InvalidTickerError (400), TradeError (400), AlreadyOnWatchlistError (409),
NotOnWatchlistError (404); see app.services.errors.
"""
