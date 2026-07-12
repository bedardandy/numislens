"""Exception handlers mapping core errors to HTTP responses."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from numislens_core import (
    CoinNotFound,
    LedgerError,
    LocationNotFound,
    ManifestError,
    MoveConflict,
    SetNotFound,
    SlotError,
    UnknownSeries,
)
from numislens_core.melt import SpotError


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(CoinNotFound)
    async def coin_not_found_handler(
        request: Request, exc: CoinNotFound
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(LocationNotFound)
    async def location_not_found_handler(
        request: Request, exc: LocationNotFound
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(SetNotFound)
    async def set_not_found_handler(
        request: Request, exc: SetNotFound
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def value_error_handler(
        request: Request, exc: ValueError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(ManifestError)
    async def manifest_error_handler(
        request: Request, exc: ManifestError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(SlotError)
    async def slot_error_handler(
        request: Request, exc: SlotError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(MoveConflict)
    async def move_conflict_handler(request: Request, exc: MoveConflict) -> JSONResponse:
        return JSONResponse(status_code=409, content={'detail': str(exc)})

    @app.exception_handler(UnknownSeries)
    async def unknown_series_handler(
        request: Request, exc: UnknownSeries
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "message": f"unknown series {exc.series!r}",
                    "known_series": exc.known,
                }
            },
        )

    @app.exception_handler(LedgerError)
    async def ledger_error_handler(
        request: Request, exc: LedgerError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(SpotError)
    async def spot_error_handler(
        request: Request, exc: SpotError
    ) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})
