"""Serve the Next.js static export with SPA fallback. Registered after all /api routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.routing import Match

_ALL_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


def _not_found() -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Not Found"})


def register_static(app: FastAPI, static_dir: Path) -> None:
    root = static_dir.resolve()

    @app.api_route("/api/{path:path}", methods=_ALL_METHODS, include_in_schema=False)
    async def api_fallback(request: Request, path: str):
        """Unknown /api paths are 404 for every method (API.md §5); a known path called
        with the wrong method stays 405."""
        for route in app.router.routes:
            if getattr(route, "endpoint", None) in (api_fallback, spa):
                continue
            match, _ = route.matches(request.scope)
            if match is not Match.NONE:  # path known, method not allowed
                return JSONResponse(status_code=405, content={"detail": "Method Not Allowed"})
        return _not_found()

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path == "api":
            return _not_found()
        index = root / "index.html"
        if path:
            candidate = (root / path).resolve()
            if candidate.is_relative_to(root):
                for option in (candidate, candidate / "index.html", Path(f"{candidate}.html")):
                    if option.is_file():
                        return FileResponse(option)
        if index.is_file():
            return FileResponse(index)
        return _not_found()
