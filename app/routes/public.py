from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response

from sqlalchemy.exc import SQLAlchemyError

from ..db import db
from ..dependencies import templates
from ..constants import (
    DEFAULT_BADGE_FONT_SIZE,
    DEFAULT_BADGE_TEXT_LOCATION,
    DEFAULT_IMAGE_COLOR,
    DEFAULT_IMAGE_FONT,
    MAX_BADGE_FONT_SIZE,
    MAX_BADGE_ID_LENGTH,
    MAX_IMAGE_LABEL_LENGTH,
    MIN_BADGE_FONT_SIZE,
)
from ..services.badge_renderer import render_badge_image


router = APIRouter(tags=["public"])
logger = logging.getLogger(__name__)


def _build_selection_form(
    *,
    font_size: Optional[Any] = None,
    image_label: Optional[str] = None,
    text_x: Optional[Any] = None,
    text_y: Optional[Any] = None,
) -> Dict[str, Any]:
    form_data: Dict[str, Any] = {
        "font_size": DEFAULT_BADGE_FONT_SIZE,
        "image_label": "",
        "text_x": "",
        "text_y": "",
    }

    if font_size is not None:
        try:
            parsed_size = int(font_size)
        except (TypeError, ValueError):
            parsed_size = DEFAULT_BADGE_FONT_SIZE
        form_data["font_size"] = max(
            MIN_BADGE_FONT_SIZE,
            min(MAX_BADGE_FONT_SIZE, parsed_size),
        )

    if image_label:
        form_data["image_label"] = image_label.strip()

    if text_x not in (None, ""):
        try:
            parsed_x = int(text_x)
        except (TypeError, ValueError):
            parsed_x = None
        else:
            form_data["text_x"] = str(max(parsed_x, 0))

    if text_y not in (None, ""):
        try:
            parsed_y = int(text_y)
        except (TypeError, ValueError):
            parsed_y = None
        else:
            form_data["text_y"] = str(max(parsed_y, 0))

    return form_data


def _render_selection_page(
    request: Request,
    *,
    profile: Optional[Dict[str, Any]],
    error: Optional[str],
    sent: bool,
    form: Optional[Dict[str, Any]] = None,
    status_code: int = status.HTTP_200_OK,
) -> Response:
    current_form = form or {}
    form_data = _build_selection_form(
        font_size=current_form.get("font_size"),
        image_label=current_form.get("image_label"),
        text_x=current_form.get("text_x"),
        text_y=current_form.get("text_y"),
    )
    return templates.TemplateResponse(
        "selection.html",
        {
            "request": request,
            "profile": profile,
            "error": error,
            "sent": sent,
            "form": form_data,
            "MIN_BADGE_FONT_SIZE": MIN_BADGE_FONT_SIZE,
            "MAX_BADGE_FONT_SIZE": MAX_BADGE_FONT_SIZE,
        },
        status_code=status_code,
    )


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
        return _render_selection_page(
            request,
            profile=None,
            error="Badge not found",
            sent=False,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    try:
        profile = await db.fetch_profile(unique_id)
    except SQLAlchemyError:
        logger.exception("Failed to load badge %s", unique_id)
        return _render_selection_page(
            request,
            profile=None,
            error="Something went wrong while retrieving your badge. Please try again.",
            sent=False,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    if profile is None:
        return _render_selection_page(
            request,
            profile=None,
            error=error or "Badge not found",
            sent=False,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return _render_selection_page(
        request,
        profile=profile,
        error=error,
        sent=sent is not None,
    )


@router.post("/badges/{unique_id}", response_class=HTMLResponse)
async def post_badge(
    request: Request,
    unique_id: str,
    image_label: str = Form(..., max_length=MAX_IMAGE_LABEL_LENGTH),
    font_size: int = Form(..., ge=MIN_BADGE_FONT_SIZE, le=MAX_BADGE_FONT_SIZE),
    text_x: Optional[str] = Form(None),
    text_y: Optional[str] = Form(None),
) -> Response:
    unique_id = unique_id.strip()
    if len(unique_id) > MAX_BADGE_ID_LENGTH:
        return _render_selection_page(
            request,
            profile=None,
            error="Badge not found",
            sent=False,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    image_label = image_label.strip()
    form_state = _build_selection_form(
        font_size=font_size,
        image_label=image_label,
        text_x=text_x,
        text_y=text_y,
    )

    def _parse_coordinate(raw_value: Optional[str]) -> Optional[int]:
        if raw_value in (None, ""):
            return None
        try:
            return max(0, int(float(raw_value)))
        except (TypeError, ValueError):
            return None

    try:
        profile = await db.fetch_profile(unique_id)
    except SQLAlchemyError:
        logger.exception("Failed to load badge %s", unique_id)
        return _render_selection_page(
            request,
            profile=None,
            error="Something went wrong while retrieving your badge. Please try again.",
            sent=False,
            form=form_state,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    if profile is None:
        return _render_selection_page(
            request,
            profile=None,
            error="Badge not found",
            sent=False,
            form=form_state,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    text_x_value = _parse_coordinate(text_x)
    text_y_value = _parse_coordinate(text_y)
    location_token = DEFAULT_BADGE_TEXT_LOCATION
    if text_x_value is not None and text_y_value is not None:
        location_token = f"{text_x_value},{text_y_value}"
        form_state = _build_selection_form(
            font_size=font_size,
            image_label=image_label,
            text_x=text_x_value,
            text_y=text_y_value,
        )

    selected_image = next(
        (image for image in profile["images"] if image["label"] == image_label),
        None,
    )

    if selected_image is None:
        return _render_selection_page(
            request,
            profile=profile,
            error="Please select a valid image.",
            sent=False,
            form=form_state,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        personalised_base64 = render_badge_image(
            image_base64=selected_image["image_base64"],
            attendee_name=profile["name"],
            font_filename=selected_image.get("image_font") or DEFAULT_IMAGE_FONT,
            font_size=form_state["font_size"],
            text_color=selected_image.get("image_color") or DEFAULT_IMAGE_COLOR,
            text_location=location_token,
        )
    except Exception:
        logger.exception("Failed to personalise image '%s' for %s", image_label, unique_id)
        return _render_selection_page(
            request,
            profile=profile,
            error="We couldn't personalise that image. Please adjust your options or try again.",
            sent=False,
            form=form_state,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    try:
        await db.enqueue_selection(
            unique_id=profile["unique_id"],
            name=profile["name"],
            image_label=selected_image["label"],
            image_base64=personalised_base64,
            image_mime_type=selected_image.get("image_mime_type") or "image/png",
            image_color=selected_image.get("image_color") or DEFAULT_IMAGE_COLOR,
            image_font=selected_image.get("image_font") or DEFAULT_IMAGE_FONT,
            font_size=form_state["font_size"],
            text_x=text_x_value,
            text_y=text_y_value,
        )
    except SQLAlchemyError:
        logger.exception("Failed to enqueue selection for %s", unique_id)
        return _render_selection_page(
            request,
            profile=profile,
            error="We couldn't save your selection right now. Please try again.",
            sent=False,
            form=form_state,
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
