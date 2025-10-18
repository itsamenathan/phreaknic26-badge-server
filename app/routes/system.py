from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse


router = APIRouter(tags=["system"])


@router.get("/healthz", response_class=JSONResponse)
async def healthcheck() -> JSONResponse:
    return JSONResponse({"status": "ok"})
