"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from .auth import require_token
from .config import Settings, resolve_token
from .errors import register_error_handlers
from .routers import coins, labels, locations, melt, sets


def create_app(
    db_path: str | Path,
    images_dir: Path | None = None,
    token: str | None = None,
) -> FastAPI:
    if token is None:
        token = resolve_token()
    if token is None:
        raise RuntimeError(
            "no bearer token configured; set NUMISLENS_TOKEN or create "
            "~/.config/numislens/token (chmod 600); generate one with: "
            'python3 -c "import secrets;print(secrets.token_urlsafe(32))"'
        )

    app = FastAPI(
        title="NumisLens Daemon",
        version="0.1.0",
        description="Local API for the NumisLens coin collection.",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
    )

    app.state.numislens_token = token
    app.state.db_path = str(db_path)
    app.state.images_dir = images_dir or Settings(db_path=db_path).images_dir

    router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_token)])

    @router.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    router.include_router(coins.router)
    router.include_router(locations.router)
    router.include_router(sets.router)
    router.include_router(melt.router)
    router.include_router(labels.router)

    app.include_router(router)
    register_error_handlers(app)

    public = Path(__file__).resolve().parents[2] / "public"
    app.mount("/", StaticFiles(directory=public, html=True), name="static")

    return app
