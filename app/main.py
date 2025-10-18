from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.staticfiles import StaticFiles

from .config import get_settings
from .db import db
from .dependencies import BASE_DIR
from .routes import admin_api, admin_pages, public, system


logger = logging.getLogger(__name__)

app = FastAPI(title="PhreakNIC 26 Badge Server", default_response_class=HTMLResponse)

static_dir = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


async def startup_event() -> None:
    settings = get_settings()
    db.configure(settings)
    await db.connect()


async def shutdown_event() -> None:
    await db.disconnect()


app.add_event_handler("startup", startup_event)
app.add_event_handler("shutdown", shutdown_event)

app.include_router(public.router)
app.include_router(admin_pages.router)
app.include_router(admin_api.router)
app.include_router(system.router)
