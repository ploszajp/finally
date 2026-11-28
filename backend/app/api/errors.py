"""Map domain errors to the {"detail": "..."} format and status codes in API.md §1."""

from __future__ import annotations

import logging
import math
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
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


def _json_safe(value: Any) -> Any:
    """Replace non-finite floats (NaN, ±Infinity echoed back as `input`) with strings,
    otherwise JSON encoding the 422 body fails and the client gets a 500."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Same shape as FastAPI's default handler (API.md §1), but always encodable.
    return JSONResponse(
        status_code=422, content={"detail": _json_safe(jsonable_encoder(exc.errors()))}
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_error)
    for exc_type, status in _STATUS.items():

        async def handler(_: Request, exc: Exception, status: int = status) -> JSONResponse:
            return JSONResponse(status_code=status, content={"detail": str(exc)})

        app.add_exception_handler(exc_type, handler)

    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.add_exception_handler(Exception, unhandled)
