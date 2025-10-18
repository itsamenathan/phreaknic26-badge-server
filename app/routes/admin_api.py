from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import Response

from ..constants import MAX_BADGE_ID_LENGTH, MAX_BADGE_NAME_LENGTH
from ..db import db
from ..dependencies import verify_credentials


router = APIRouter(prefix="/admin/api", tags=["admin-api"])
logger = logging.getLogger(__name__)


class BadgePayload(BaseModel):
    unique_id: str = Field(..., min_length=1, max_length=MAX_BADGE_ID_LENGTH)
    name: str = Field(..., min_length=1, max_length=MAX_BADGE_NAME_LENGTH)

    @field_validator("unique_id", "name", mode="before")
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

    try:
        outcome = await db.create_or_update_badge(unique_id=unique_id, name=name)
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
