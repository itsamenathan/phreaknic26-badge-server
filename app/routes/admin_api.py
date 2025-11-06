from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.responses import Response

from ..constants import (
    MAX_BADGE_ID_LENGTH,
    MAX_BADGE_NAME_LENGTH,
    MAX_BADGE_MAC_ADDRESS_LENGTH,
)
from ..db import db
from ..dependencies import verify_credentials
from ..utils import normalise_mac_address


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
            {"detail": "Invalid MAC address. Use format AA:BB:CC:DD:EE:FF."},
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


@router.get("/work-items/next", response_class=JSONResponse)
async def get_work_item(_credentials=Depends(verify_credentials)) -> Response:
    try:
        work_item = await db.get_oldest_work()
    except SQLAlchemyError:
        logger.exception("Failed to fetch work item")
        return JSONResponse(
            {"detail": "Failed to fetch work item"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    if work_item is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    work_item = dict(work_item)
    work_item["badge_id"] = work_item.pop("unique_id")
    return JSONResponse(work_item)


@router.get("/badges/mac/{mac_address}", response_class=JSONResponse)
async def admin_get_badge_by_mac(
    mac_address: str,
    _credentials=Depends(verify_credentials),
) -> Response:
    normalised = normalise_mac_address(mac_address)
    if normalised is None:
        return JSONResponse(
            {"detail": "Invalid MAC address. Use format AA:BB:CC:DD:EE:FF."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        profile = await db.fetch_profile_by_mac(normalised)
    except SQLAlchemyError:
        logger.exception("Failed to fetch badge for MAC %s", mac_address)
        return JSONResponse(
            {"detail": "Failed to look up that badge. Please try again."},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if profile is None:
        return JSONResponse(
            {"detail": "Badge not found."},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return JSONResponse(profile)
