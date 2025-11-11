from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

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
            {
                "detail": "Invalid MAC address. Use format AA:BB:CC:DD:EE:FF:GG:HH."
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
