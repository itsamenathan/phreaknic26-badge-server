from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response

from sqlalchemy.exc import SQLAlchemyError

from ..db import db
from ..dependencies import templates
from ..constants import (
    DEFAULT_IMAGE_COLOR,
    DEFAULT_IMAGE_FONT,
    MAX_BADGE_ID_LENGTH,
    MAX_IMAGE_LABEL_LENGTH,
)


router = APIRouter(tags=["public"])
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def badge_lookup_form(
    request: Request,
) -> Response:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "form": {"unique_id": ""},
            "error": None,
            "MAX_BADGE_ID_LENGTH": MAX_BADGE_ID_LENGTH,
        },
    )


@router.post("/", response_class=HTMLResponse)
async def badge_lookup_submit(
    request: Request,
    unique_id: str = Form(...),
) -> Response:
    unique_id = (unique_id or "").strip()
    if not unique_id:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "form": {"unique_id": unique_id},
                "error": "Please enter a badge ID.",
                "MAX_BADGE_ID_LENGTH": MAX_BADGE_ID_LENGTH,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if len(unique_id) > MAX_BADGE_ID_LENGTH:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "form": {"unique_id": unique_id},
                "error": f"Badge ID must be {MAX_BADGE_ID_LENGTH} characters or fewer.",
                "MAX_BADGE_ID_LENGTH": MAX_BADGE_ID_LENGTH,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        profile = await db.fetch_profile(unique_id)
    except SQLAlchemyError:
        logger.exception("Failed to check badge %s during lookup", unique_id)
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "form": {"unique_id": unique_id},
                "error": "Something went wrong while looking up your badge. Please try again.",
                "MAX_BADGE_ID_LENGTH": MAX_BADGE_ID_LENGTH,
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if profile is None:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "form": {"unique_id": unique_id},
                "error": "Badge not found. Please check the ID and try again.",
                "MAX_BADGE_ID_LENGTH": MAX_BADGE_ID_LENGTH,
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return RedirectResponse(
        request.url_for("get_badge", unique_id=unique_id),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/badges/{unique_id}", response_class=HTMLResponse)
async def get_badge(
    request: Request,
    unique_id: str,
    sent: Optional[str] = None,
    error: Optional[str] = None,
) -> Response:
    unique_id = unique_id.strip()
    if len(unique_id) > MAX_BADGE_ID_LENGTH:
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

    try:
        profile = await db.fetch_profile(unique_id)
    except SQLAlchemyError:
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


@router.post("/badges/{unique_id}", response_class=HTMLResponse)
async def post_badge(
    request: Request,
    unique_id: str,
    image_label: str = Form(..., max_length=MAX_IMAGE_LABEL_LENGTH),
) -> Response:
    unique_id = unique_id.strip()
    if len(unique_id) > MAX_BADGE_ID_LENGTH:
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

    try:
        profile = await db.fetch_profile(unique_id)
    except SQLAlchemyError:
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
            image_color=selected_image.get("image_color") or DEFAULT_IMAGE_COLOR,
            image_font=selected_image.get("image_font") or DEFAULT_IMAGE_FONT,
        )
    except SQLAlchemyError:
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


# Legacy routes kept for backward compatibility.
router.add_api_route(
    "/id={unique_id}",
    get_badge,
    methods=["GET"],
    response_class=HTMLResponse,
    include_in_schema=False,
    name="legacy_get_badge",
)
router.add_api_route(
    "/id={unique_id}",
    post_badge,
    methods=["POST"],
    response_class=HTMLResponse,
    include_in_schema=False,
    name="legacy_post_badge",
)
