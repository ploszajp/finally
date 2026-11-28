"""Serve the Next.js static export with SPA fallback. Registered after all /api routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse


def register_static(app: FastAPI, static_dir: Path) -> None:
    root = static_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path == "api" or path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        index = root / "index.html"
        if path:
            candidate = (root / path).resolve()
            if candidate.is_relative_to(root):
                for option in (candidate, candidate / "index.html", Path(f"{candidate}.html")):
                    if option.is_file():
                        return FileResponse(option)
        if index.is_file():
            return FileResponse(index)
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
