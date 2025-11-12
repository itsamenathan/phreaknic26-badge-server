from __future__ import annotations

import base64
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..constants import (
    MAX_BADGE_ID_LENGTH,
    MAX_BADGE_NAME_LENGTH,
    MAX_BADGE_MAC_ADDRESS_LENGTH,
    MAX_IMAGE_LABEL_LENGTH,
    MAX_IMAGE_SECRET_CODE_LENGTH,
    IMAGE_COLOR_CHOICES,
)
from ..db import db
from ..dependencies import verify_credentials
from ..utils import load_font_choices, normalise_mac_address


router = APIRouter(prefix="/admin/api", tags=["admin-api"])
logger = logging.getLogger(__name__)


class BadgePayload(BaseModel):
    unique_id: str = Field(..., min_length=1, max_length=MAX_BADGE_ID_LENGTH)
    name: str = Field(..., min_length=1, max_length=MAX_BADGE_NAME_LENGTH)
    mac_address: str = Field(..., min_length=1, max_length=MAX_BADGE_MAC_ADDRESS_LENGTH)

    @field_validator("unique_id", "name", "mac_address", mode="before")
    @classmethod
    def strip_whitespace(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
        return value


def _form_to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


@router.post("/badges", response_class=JSONResponse)
async def admin_create_badge_api(
    payload: BadgePayload,
    _credentials=Depends(verify_credentials),
) -> Response:
    unique_id = payload.unique_id
    name = payload.name
    mac_address = normalise_mac_address(payload.mac_address)
    if mac_address is None:
        return JSONResponse(
            {
                "detail": "Invalid MAC address. Use format AA:BB:CC:DD:EE:FF:00:111."
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        outcome = await db.create_or_update_badge(
            unique_id=unique_id,
            name=name,
            mac_address=mac_address,
        )
    except IntegrityError:
        logger.exception("MAC address conflict for badge %s", unique_id)
        return JSONResponse(
            {"detail": "That MAC address is already assigned to another badge."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except SQLAlchemyError:
        logger.exception("Failed to create or update badge %s via API", unique_id)
        return JSONResponse(
            {"detail": "Something went wrong while saving the badge. Please try again."},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    status_code = (
        status.HTTP_201_CREATED if outcome == "created" else status.HTTP_200_OK
    )
    return JSONResponse(
        {
            "status": outcome,
            "unique_id": unique_id,
            "name": name,
            "mac_address": mac_address,
            "message": (
                "Badge created successfully."
                if outcome == "created"
                else "Badge updated successfully."
            ),
        },
        status_code=status_code,
    )


@router.post("/images", response_class=JSONResponse)
async def admin_upload_badge_image_api(
    image_label: str = Form(..., max_length=MAX_IMAGE_LABEL_LENGTH),
    image_file: UploadFile = File(...),
    image_color: str = Form(...),
    image_font: str = Form(...),
    secret_code: Optional[str] = Form(None, max_length=MAX_IMAGE_SECRET_CODE_LENGTH),
    requires_secret_code: Optional[str] = Form(None),
    display_order: Optional[str] = Form("0"),
    _credentials=Depends(verify_credentials),
) -> Response:
    image_label = (image_label or "").strip()
    image_color = (image_color or "").strip().lower()
    image_font = (image_font or "").strip()
    secret_code = (secret_code or "").strip()
    requires_secret_code_value = _form_to_bool(requires_secret_code)

    try:
        display_order_value = int(display_order) if display_order not in (None, "") else 0
    except (TypeError, ValueError):
        return JSONResponse(
            {"detail": "Display order must be a whole number."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not image_label:
        return JSONResponse(
            {"detail": "Image label is required."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if len(image_label) > MAX_IMAGE_LABEL_LENGTH:
        return JSONResponse(
            {
                "detail": (
                    f"Image label must be {MAX_IMAGE_LABEL_LENGTH} characters or fewer."
                )
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if image_color not in IMAGE_COLOR_CHOICES:
        return JSONResponse(
            {"detail": "Please choose a valid color option."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    font_choices, font_error = load_font_choices()
    if image_font not in font_choices:
        error_message = (
            "Please choose a valid font option."
            if not font_error
            else "Font options are unavailable right now. Please try again."
        )
        return JSONResponse(
            {"detail": error_message},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if requires_secret_code_value and not secret_code:
        return JSONResponse(
            {"detail": "Secret code is required when locking the image."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if len(secret_code) > MAX_IMAGE_SECRET_CODE_LENGTH:
        return JSONResponse(
            {
                "detail": (
                    f"Secret code must be {MAX_IMAGE_SECRET_CODE_LENGTH} characters or fewer."
                )
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        content = await image_file.read()
    except Exception:
        logger.exception("Failed to read uploaded file for %s", image_label or "<unknown>")
        return JSONResponse(
            {"detail": "Could not read the uploaded file."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not content:
        return JSONResponse(
            {"detail": "Uploaded file is empty."},
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
        logger.exception("Failed to store gallery image %s via API", image_label)
        return JSONResponse(
            {"detail": "Something went wrong while saving the image. Please try again."},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    status_code_value = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    outcome = "created" if created else "updated"
    message = (
        "Badge image uploaded successfully."
        if created
        else "Badge image updated successfully."
    )
    return JSONResponse(
        {
            "status": outcome,
            "message": message,
            "image_label": image_label,
            "image_color": image_color,
            "image_font": image_font,
            "requires_secret_code": requires_secret_code_value,
            "display_order": display_order_value,
            "secret_code_set": bool(secret_code),
        },
        status_code=status_code_value,
    )
