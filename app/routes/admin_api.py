from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, status
from fastapi.responses import JSONResponse
from starlette.responses import Response

from sqlalchemy.exc import SQLAlchemyError

from ..db import db
from ..dependencies import verify_credentials


router = APIRouter(prefix="/admin/api", tags=["admin-api"])
logger = logging.getLogger(__name__)


@router.post("/badges", response_class=JSONResponse)
async def admin_create_badge_api(
    payload: Dict[str, Any] = Body(...),
    _credentials=Depends(verify_credentials),
) -> Response:
    unique_id = (payload.get("unique_id") or "").strip()
    name = (payload.get("name") or "").strip()

    if not unique_id or not name:
        return JSONResponse(
            {"detail": "Both unique_id and name are required."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

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
    return JSONResponse(work_item)
