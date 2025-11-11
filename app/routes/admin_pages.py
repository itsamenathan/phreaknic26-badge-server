from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..constants import (
    DEFAULT_IMAGE_COLOR,
    DEFAULT_IMAGE_FONT,
    MAX_BADGE_ID_LENGTH,
    MAX_BADGE_NAME_LENGTH,
    MAX_BADGE_MAC_ADDRESS_LENGTH,
    MAX_IMAGE_LABEL_LENGTH,
    MAX_IMAGE_SECRET_CODE_LENGTH,
    IMAGE_COLOR_CHOICES,
    FONT_FILE_EXTENSIONS,
)
from ..db import db
from ..dependencies import templates, verify_credentials
from ..logs import get_recent_logs
from ..utils import normalise_mac_address


router = APIRouter(
    prefix="/admin",
    tags=["admin-pages"],
    dependencies=[Depends(verify_credentials)],
)

logger = logging.getLogger(__name__)
FONTS_DIR = (Path(__file__).resolve().parent.parent / "static" / "fonts").resolve()

def _load_font_choices() -> Tuple[List[str], Optional[str]]:
    try:
        fonts_path = FONTS_DIR
        choices = []
        if fonts_path.exists():
            entries = {
                entry.name
                for entry in fonts_path.iterdir()
                if (
                    entry.is_file()
                    and not entry.name.startswith(".")
                    and entry.suffix.lower() in FONT_FILE_EXTENSIONS
                )
            }
            choices = sorted(entries, key=str.lower)
        if not choices:
            choices = [DEFAULT_IMAGE_FONT]
        if DEFAULT_IMAGE_FONT not in choices:
            choices.insert(0, DEFAULT_IMAGE_FONT)
        return choices, None
    except OSError:
        logger.exception("Failed to read font directory %s", FONTS_DIR)
        return [DEFAULT_IMAGE_FONT], "We couldn't load the font options. Please refresh the page."


async def _load_available_images() -> Tuple[List[Dict[str, Optional[str]]], Optional[str]]:
    try:
        images = await db.list_available_images()
        return images, None
    except SQLAlchemyError:
        logger.exception("Failed to load available images")
        return [], "We couldn't load the existing images. Please refresh the page."


async def _render_admin_upload(
    request: Request,
    form_data: Dict[str, str],
    *,
    success: Optional[str],
    error: Optional[str],
    status_code: int = status.HTTP_200_OK,
) -> Response:
    images, load_error = await _load_available_images()
    next_display_order = 0
    if images:
        next_display_order = max((image.get("display_order") or 0) for image in images) + 1
    full_form_data = {
        "image_label": "",
        "image_color": DEFAULT_IMAGE_COLOR,
        "image_font": DEFAULT_IMAGE_FONT,
        "requires_secret_code": True,
        "secret_code": "",
        "display_order": next_display_order,
        **form_data,
    }
    try:
        current_display_order = full_form_data.get("display_order")
        if current_display_order in (None, ""):
            full_form_data["display_order"] = next_display_order
        else:
            full_form_data["display_order"] = int(current_display_order)
    except (TypeError, ValueError):
        full_form_data["display_order"] = next_display_order
    full_form_data["requires_secret_code"] = bool(full_form_data["requires_secret_code"])
    font_choices, font_error = _load_font_choices()
    if full_form_data["image_font"] not in font_choices:
        full_form_data["image_font"] = font_choices[0]
    error_messages = [msg for msg in (error, load_error, font_error) if msg]
    combined_error = "; ".join(error_messages) if error_messages else None
    return templates.TemplateResponse(
        "admin_upload.html",
        {
            "request": request,
            "form": full_form_data,
            "success": success,
            "error": combined_error,
            "images": images,
            "MAX_IMAGE_LABEL_LENGTH": MAX_IMAGE_LABEL_LENGTH,
            "MAX_IMAGE_SECRET_CODE_LENGTH": MAX_IMAGE_SECRET_CODE_LENGTH,
            "IMAGE_COLOR_CHOICES": IMAGE_COLOR_CHOICES,
            "IMAGE_FONT_CHOICES": font_choices,
            "DEFAULT_IMAGE_FONT": DEFAULT_IMAGE_FONT,
        },
        status_code=status_code,
    )


async def _render_admin_create_badge(
    request: Request,
    form_data: Dict[str, str],
    *,
    success: Optional[str],
    error: Optional[str],
    status_code: int = status.HTTP_200_OK,
) -> Response:
    badges: List[Dict[str, Any]] = []
    load_error: Optional[str] = None
    try:
        badges = await db.list_badges()
    except SQLAlchemyError:
        logger.exception("Failed to load badges")
        load_error = "We couldn't load the existing badges. Please refresh the page."

    error_messages = [msg for msg in (error, load_error) if msg]
    combined_error = "; ".join(error_messages) if error_messages else None
    return templates.TemplateResponse(
        "admin_create_badge.html",
        {
            "request": request,
            "form": form_data,
            "success": success,
            "error": combined_error,
            "badges": badges,
            "MAX_BADGE_ID_LENGTH": MAX_BADGE_ID_LENGTH,
            "MAX_BADGE_NAME_LENGTH": MAX_BADGE_NAME_LENGTH,
            "MAX_BADGE_MAC_ADDRESS_LENGTH": MAX_BADGE_MAC_ADDRESS_LENGTH,
        },
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
async def admin_index(request: Request) -> Response:
    return templates.TemplateResponse(
        "admin_index.html",
        {
            "request": request,
        },
    )


@router.get("/logs", response_class=HTMLResponse, name="admin_logs_page")
async def admin_logs_page(request: Request, limit: int = 200) -> Response:
    safe_limit = max(10, min(limit, 1000))
    logs = get_recent_logs(safe_limit)
    return templates.TemplateResponse(
        "admin_logs.html",
        {
            "request": request,
            "logs": logs,
            "limit": safe_limit,
        },
    )


@router.get("/images", response_class=HTMLResponse)
async def admin_images_form(
    request: Request,
    image_label: Optional[str] = None,
    success: Optional[str] = None,
    error: Optional[str] = None,
) -> Response:
    form_data = {
        "image_label": (image_label or "")[:MAX_IMAGE_LABEL_LENGTH],
        "image_color": DEFAULT_IMAGE_COLOR,
        "image_font": DEFAULT_IMAGE_FONT,
        "requires_secret_code": True,
        "secret_code": "",
        "display_order": None,
    }
    return await _render_admin_upload(
        request,
        form_data,
        success=success,
        error=error,
    )


@router.post("/images", response_class=HTMLResponse)
async def admin_images_upload(
    request: Request,
    image_label: str = Form(..., max_length=MAX_IMAGE_LABEL_LENGTH),
    image_file: UploadFile = File(...),
    image_color: str = Form(...),
    image_font: str = Form(...),
    secret_code: Optional[str] = Form(None, max_length=MAX_IMAGE_SECRET_CODE_LENGTH),
    requires_secret_code: Optional[bool] = Form(False),
    display_order: Optional[str] = Form("0"),
) -> Response:
    image_label = image_label.strip()
    image_color = image_color.strip().lower()
    image_font = image_font.strip()
    secret_code = (secret_code or "").strip()
    requires_secret_code_value = bool(requires_secret_code)
    try:
        display_order_value = int(display_order) if display_order not in (None, "") else 0
    except (TypeError, ValueError):
        return await _render_admin_upload(
            request,
            {
                "image_label": image_label,
                "image_color": image_color,
                "image_font": image_font,
                "secret_code": secret_code,
                "requires_secret_code": requires_secret_code_value,
                "display_order": display_order or 0,
            },
            success=None,
            error="Display order must be a whole number.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    form_data = {
        "image_label": image_label,
        "image_color": image_color,
        "image_font": image_font,
        "secret_code": secret_code,
        "requires_secret_code": requires_secret_code_value,
        "display_order": display_order_value,
    }

    font_choices, font_error = _load_font_choices()

    if not image_label:
        return await _render_admin_upload(
            request,
            form_data,
            success=None,
            error="Image label is required.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if image_color not in IMAGE_COLOR_CHOICES:
        return await _render_admin_upload(
            request,
            form_data,
            success=None,
            error="Please choose a valid color option.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if image_font not in font_choices:
        error_message = (
            "Please choose a valid font option."
            if not font_error
            else "Font options are unavailable right now. Please refresh the page."
        )
        return await _render_admin_upload(
            request,
            form_data,
            success=None,
            error=error_message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if len(image_label) > MAX_IMAGE_LABEL_LENGTH:
        return await _render_admin_upload(
            request,
            form_data,
            success=None,
            error=f"Image label must be {MAX_IMAGE_LABEL_LENGTH} characters or fewer.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if requires_secret_code_value and not secret_code:
        return await _render_admin_upload(
            request,
            form_data,
            success=None,
            error="Secret code is required when locking the image.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        content = await image_file.read()
    except Exception:
        logger.exception("Failed to read uploaded file for %s", image_label)
        return await _render_admin_upload(
            request,
            form_data,
            success=None,
            error="Could not read the uploaded file.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not content:
        return await _render_admin_upload(
            request,
            form_data,
            success=None,
            error="Uploaded file is empty.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    image_base64 = base64.b64encode(content).decode("ascii")
    image_mime_type = image_file.content_type or "image/png"

    try:
        created = await db.store_available_image(
            image_label=image_label,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
            image_color=image_color,
            image_font=image_font,
            secret_code=secret_code,
            requires_secret_code=requires_secret_code_value,
            display_order=display_order_value,
        )
    except SQLAlchemyError:
        logger.exception("Failed to store gallery image %s", image_label)
        return await _render_admin_upload(
            request,
            form_data,
            success=None,
            error="Something went wrong while saving the image. Please try again.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    query_params = urlencode(
        {
            "success": "Badge image uploaded successfully."
            if created
            else "Badge image updated successfully.",
            "image_label": image_label,
        }
    )
    redirect_url = f"{request.url_for('admin_images_form')}?{query_params}"
    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/images/update", response_class=HTMLResponse)
async def admin_images_update(
    request: Request,
    image_label: str = Form(..., max_length=MAX_IMAGE_LABEL_LENGTH),
    image_color: str = Form(...),
    image_font: str = Form(...),
    secret_code: Optional[str] = Form(None, max_length=MAX_IMAGE_SECRET_CODE_LENGTH),
    requires_secret_code: Optional[bool] = Form(False),
    display_order: Optional[str] = Form("0"),
) -> Response:
    image_label = image_label.strip()
    image_color = image_color.strip().lower()
    image_font = image_font.strip()
    secret_code = (secret_code or "").strip()
    requires_secret_code_value = bool(requires_secret_code)
    try:
        display_order_value = int(display_order) if display_order not in (None, "") else 0
    except (TypeError, ValueError):
        return await _render_admin_upload(
            request,
            {
                "image_label": "",
                "image_color": DEFAULT_IMAGE_COLOR,
                "image_font": DEFAULT_IMAGE_FONT,
                "requires_secret_code": True,
                "secret_code": "",
                "display_order": 0,
            },
            success=None,
            error="Display order must be a whole number.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    font_choices, font_error = _load_font_choices()

    if not image_label:
        return await _render_admin_upload(
            request,
            {
                "image_label": "",
                "image_color": DEFAULT_IMAGE_COLOR,
                "image_font": DEFAULT_IMAGE_FONT,
                "requires_secret_code": True,
                "secret_code": "",
                "display_order": 0,
            },
            success=None,
            error="Image label is required.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if image_color not in IMAGE_COLOR_CHOICES:
        return await _render_admin_upload(
            request,
            {
                "image_label": "",
                "image_color": DEFAULT_IMAGE_COLOR,
                "image_font": DEFAULT_IMAGE_FONT,
                "requires_secret_code": True,
                "secret_code": "",
                "display_order": 0,
            },
            success=None,
            error="Please choose a valid color option.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if image_font not in font_choices:
        error_message = (
            "Please choose a valid font option."
            if not font_error
            else "Font options are unavailable right now. Please refresh the page."
        )
        return await _render_admin_upload(
            request,
            {
                "image_label": "",
                "image_color": DEFAULT_IMAGE_COLOR,
                "image_font": DEFAULT_IMAGE_FONT,
                "requires_secret_code": True,
                "secret_code": "",
                "display_order": 0,
            },
            success=None,
            error=error_message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if requires_secret_code_value and not secret_code:
        return await _render_admin_upload(
            request,
            {
                "image_label": "",
                "image_color": DEFAULT_IMAGE_COLOR,
                "image_font": DEFAULT_IMAGE_FONT,
                "requires_secret_code": True,
                "secret_code": "",
                "display_order": 0,
            },
            success=None,
            error="Secret code is required when locking the image.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        updated = await db.update_available_image_metadata(
            image_label=image_label,
            image_color=image_color,
            image_font=image_font,
            secret_code=secret_code,
            requires_secret_code=requires_secret_code_value,
            display_order=display_order_value,
        )
    except SQLAlchemyError:
        logger.exception("Failed to update gallery image %s", image_label)
        return await _render_admin_upload(
            request,
            {
                "image_label": "",
                "image_color": DEFAULT_IMAGE_COLOR,
                "image_font": DEFAULT_IMAGE_FONT,
                "requires_secret_code": True,
                "secret_code": "",
                "display_order": 0,
            },
            success=None,
            error="Something went wrong while updating the image. Please try again.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if not updated:
        return await _render_admin_upload(
            request,
            {
                "image_label": "",
                "image_color": DEFAULT_IMAGE_COLOR,
                "image_font": DEFAULT_IMAGE_FONT,
                "requires_secret_code": True,
                "secret_code": "",
                "display_order": 0,
            },
            success=None,
            error="The requested image could not be found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    query_params = urlencode({"success": f"{image_label} updated successfully."})
    redirect_url = f"{request.url_for('admin_images_form')}?{query_params}"
    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/images/delete", response_class=HTMLResponse)
async def admin_images_delete(
    request: Request,
    image_label: str = Form(..., max_length=MAX_IMAGE_LABEL_LENGTH),
) -> Response:
    image_label = image_label.strip()
    if not image_label:
        query_params = urlencode({"error": "Image label is required to delete an image."})
        redirect_url = f"{request.url_for('admin_images_form')}?{query_params}"
        return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    if len(image_label) > MAX_IMAGE_LABEL_LENGTH:
        query_params = urlencode(
            {
                "error": f"Image label must be {MAX_IMAGE_LABEL_LENGTH} characters or fewer.",
                "image_label": "",
            }
        )
        redirect_url = f"{request.url_for('admin_images_form')}?{query_params}"
        return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    try:
        deleted = await db.delete_available_image(image_label)
    except SQLAlchemyError:
        logger.exception("Failed to delete gallery image %s", image_label)
        return await _render_admin_upload(
            request,
            {
                "image_label": "",
                "image_color": DEFAULT_IMAGE_COLOR,
                "image_font": DEFAULT_IMAGE_FONT,
            },
            success=None,
            error="Something went wrong while deleting the image. Please try again.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    query_params = (
        {"success": "Badge image deleted successfully."}
        if deleted
        else {"error": "The requested image could not be found."}
    )
    redirect_url = f"{request.url_for('admin_images_form')}?{urlencode(query_params)}"
    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/badges", response_class=HTMLResponse)
async def admin_badges_form(
    request: Request,
    unique_id: Optional[str] = None,
    name: Optional[str] = None,
    mac_address: Optional[str] = None,
    success: Optional[str] = None,
    error: Optional[str] = None,
) -> Response:
    form_data = {
        "unique_id": (unique_id or "")[:MAX_BADGE_ID_LENGTH],
        "name": (name or "")[:MAX_BADGE_NAME_LENGTH],
        "mac_address": (mac_address or "")[:MAX_BADGE_MAC_ADDRESS_LENGTH],
    }
    return await _render_admin_create_badge(
        request,
        form_data,
        success=success,
        error=error,
    )


@router.post("/badges", response_class=HTMLResponse)
async def admin_badges_submit(
    request: Request,
    unique_id: str = Form(..., max_length=MAX_BADGE_ID_LENGTH),
    original_unique_id: Optional[str] = Form(None, max_length=MAX_BADGE_ID_LENGTH),
    name: str = Form(..., max_length=MAX_BADGE_NAME_LENGTH),
    mac_address: str = Form(..., max_length=MAX_BADGE_MAC_ADDRESS_LENGTH),
) -> Response:
    unique_id = unique_id.strip()
    name = name.strip()
    mac_address = mac_address.strip()
    original_unique_id = (original_unique_id or unique_id).strip()
    form_data = {"unique_id": unique_id, "name": name, "mac_address": mac_address}

    if not unique_id or not name:
        return await _render_admin_create_badge(
            request,
            form_data,
            success=None,
            error="Both badge ID and name are required.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not mac_address:
        return await _render_admin_create_badge(
            request,
            form_data,
            success=None,
            error="MAC address is required.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if len(unique_id) > MAX_BADGE_ID_LENGTH:
        return await _render_admin_create_badge(
            request,
            form_data,
            success=None,
            error=f"Badge ID must be {MAX_BADGE_ID_LENGTH} characters or fewer.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if len(name) > MAX_BADGE_NAME_LENGTH:
        return await _render_admin_create_badge(
            request,
            form_data,
            success=None,
            error=f"Name must be {MAX_BADGE_NAME_LENGTH} characters or fewer.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    normalised_mac = normalise_mac_address(mac_address)
    if normalised_mac is None:
        return await _render_admin_create_badge(
            request,
            form_data,
            success=None,
            error="Please enter a valid MAC address (e.g. AA:BB:CC:DD:EE:FF:GG:HH).",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    form_data["mac_address"] = normalised_mac

    if unique_id != original_unique_id:
        try:
            id_result = await db.update_badge_unique_id(original_unique_id, unique_id)
        except IntegrityError:
            logger.exception("Conflict while updating badge id %s -> %s", original_unique_id, unique_id)
            return await _render_admin_create_badge(
                request,
                form_data,
                success=None,
                error="That badge ID is already in use.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        except SQLAlchemyError:
            logger.exception("Failed to update badge id %s -> %s", original_unique_id, unique_id)
            return await _render_admin_create_badge(
                request,
                form_data,
                success=None,
                error="We couldn't update the badge ID right now. Please try again.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if id_result == "not_found":
            return await _render_admin_create_badge(
                request,
                form_data,
                success=None,
                error="The original badge ID could not be found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if id_result == "conflict":
            return await _render_admin_create_badge(
                request,
                form_data,
                success=None,
                error="That badge ID is already in use.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    try:
        outcome = await db.create_or_update_badge(
            unique_id=unique_id,
            name=name,
            mac_address=normalised_mac,
        )
    except IntegrityError:
        logger.exception("MAC address conflict for badge %s", unique_id)
        return await _render_admin_create_badge(
            request,
            form_data,
            success=None,
            error="That MAC address is already assigned to another badge.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except SQLAlchemyError:
        logger.exception("Failed to create or update badge %s", unique_id)
        return await _render_admin_create_badge(
            request,
            form_data,
            success=None,
            error="Something went wrong while saving the badge. Please try again.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    message = (
        "Badge created successfully."
        if outcome == "created"
        else "Badge updated successfully."
    )
    query_params = urlencode(
        {
            "success": message,
            "unique_id": unique_id,
            "name": name,
            "mac_address": normalised_mac,
        }
    )
    redirect_url = f"{request.url_for('admin_badges_form')}?{query_params}"
    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/badges/delete", response_class=HTMLResponse)
async def admin_badges_delete(
    request: Request,
    unique_id: str = Form(..., max_length=MAX_BADGE_ID_LENGTH),
) -> Response:
    unique_id = unique_id.strip()
    form_data = {"unique_id": "", "name": "", "mac_address": ""}

    if not unique_id:
        return await _render_admin_create_badge(
            request,
            form_data,
            success=None,
            error="A badge ID is required to delete a badge.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        deleted = await db.delete_badge(unique_id)
    except SQLAlchemyError:
        logger.exception("Failed to delete badge %s", unique_id)
        return await _render_admin_create_badge(
            request,
            form_data,
            success=None,
            error="Something went wrong while deleting the badge. Please try again.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if deleted:
        params = urlencode({"success": f"Badge {unique_id} deleted."})
    else:
        params = urlencode({"error": "The requested badge could not be found."})

    redirect_url = f"{request.url_for('admin_badges_form')}?{params}"
    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)
