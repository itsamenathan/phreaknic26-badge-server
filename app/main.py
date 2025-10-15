from __future__ import annotations

import secrets
import logging
from pathlib import Path
from typing import Dict, Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from asyncpg import PostgresError

from .config import get_settings
from .db import db


app = FastAPI(title="PhreakNIC 26 Badge Server", default_response_class=HTMLResponse)

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

static_dir = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

security = HTTPBasic()
logger = logging.getLogger(__name__)


async def startup_event() -> None:
    settings = get_settings()
    db.configure(settings)
    await db.connect()


async def shutdown_event() -> None:
    await db.disconnect()


app.add_event_handler("startup", startup_event)
app.add_event_handler("shutdown", shutdown_event)


def verify_credentials(
    credentials: HTTPBasicCredentials = Depends(security),
) -> HTTPBasicCredentials:
    settings = get_settings()
    correct_username = secrets.compare_digest(
        credentials.username or "",
        settings.basic_auth_username,
    )
    correct_password = secrets.compare_digest(
        credentials.password or "",
        settings.basic_auth_password,
    )
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials


@app.get("/id={unique_id}", response_class=HTMLResponse)
async def get_badge(
    request: Request,
    unique_id: str,
    sent: Optional[str] = None,
    error: Optional[str] = None,
) -> Response:
    try:
        profile = await db.fetch_profile(unique_id)
    except PostgresError as exc:
        logger.exception("Failed to load badge %s", unique_id)
        return templates.TemplateResponse(
            "selection.html",
            {
                "request": request,
                "profile": None,
                "error": "Something went wrong while retrieving your badge. Please try again.",
                "sent": False,
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    if profile is None:
        return templates.TemplateResponse(
            "selection.html",
            {
                "request": request,
                "profile": None,
                "error": error or "Badge not found",
                "sent": False,
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return templates.TemplateResponse(
        "selection.html",
        {
            "request": request,
            "profile": profile,
            "error": error,
            "sent": bool(sent),
        },
    )


@app.post("/id={unique_id}", response_class=HTMLResponse)
async def post_badge(
    request: Request,
    unique_id: str,
    image_label: str = Form(...),
) -> Response:
    try:
        profile = await db.fetch_profile(unique_id)
    except PostgresError:
        logger.exception("Failed to load badge %s", unique_id)
        return templates.TemplateResponse(
            "selection.html",
            {
                "request": request,
                "profile": None,
                "error": "Something went wrong while retrieving your badge. Please try again.",
                "sent": False,
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    if profile is None:
        return templates.TemplateResponse(
            "selection.html",
            {
                "request": request,
                "profile": None,
                "error": "Badge not found",
                "sent": False,
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    selected_image = next(
        (image for image in profile["images"] if image["label"] == image_label),
        None,
    )

    if selected_image is None:
        return templates.TemplateResponse(
            "selection.html",
            {
                "request": request,
                "profile": profile,
                "error": "Please select a valid image.",
                "sent": False,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        await db.enqueue_selection(
            unique_id=profile["unique_id"],
            name=profile["name"],
            image_label=selected_image["label"],
            image_base64=selected_image["image_base64"],
            image_mime_type=selected_image.get("image_mime_type") or "image/png",
        )
    except PostgresError:
        logger.exception("Failed to enqueue selection for %s", unique_id)
        return templates.TemplateResponse(
            "selection.html",
            {
                "request": request,
                "profile": profile,
                "error": "We couldn't save your selection right now. Please try again.",
                "sent": False,
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    redirect_url = request.url_for("get_badge", unique_id=unique_id)
    redirect_url = f"{redirect_url}?sent=1"
    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@app.get("/get-work", response_class=JSONResponse)
async def get_work(
    credentials: HTTPBasicCredentials = Depends(verify_credentials),
) -> Response:
    try:
        work_item = await db.get_oldest_work()
    except PostgresError:
        logger.exception("Failed to fetch work item")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch work item",
        )
    if work_item is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return JSONResponse(work_item)


@app.get("/healthz", response_class=JSONResponse)
async def healthcheck() -> Dict[str, str]:
    return {"status": "ok"}
