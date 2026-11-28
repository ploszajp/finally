"""Map domain errors to the {"detail": "..."} format and status codes in API.md §1."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.market import InvalidTickerError
from app.services.errors import AlreadyOnWatchlistError, NotOnWatchlistError, TradeError

logger = logging.getLogger(__name__)

_STATUS: dict[type[Exception], int] = {
    InvalidTickerError: 400,
    TradeError: 400,
    AlreadyOnWatchlistError: 409,
    NotOnWatchlistError: 404,
}


def register_error_handlers(app: FastAPI) -> None:
    for exc_type, status in _STATUS.items():

        async def handler(_: Request, exc: Exception, status: int = status) -> JSONResponse:
            return JSONResponse(status_code=status, content={"detail": str(exc)})

        app.add_exception_handler(exc_type, handler)

    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.add_exception_handler(Exception, unhandled)
