from __future__ import annotations

import base64
import logging
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from sqlalchemy.exc import SQLAlchemyError

from .config import get_settings
from .db import db


app = FastAPI(title="PhreakNIC 26 Badge Server", default_response_class=HTMLResponse)

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

static_dir = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

security = HTTPBasic()
logger = logging.getLogger(__name__)

QUEUE_PAGE_LIMIT = 50


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
    error_messages = [msg for msg in (error, load_error) if msg]
    combined_error = "; ".join(error_messages) if error_messages else None
    return templates.TemplateResponse(
        "admin_upload.html",
        {
            "request": request,
            "form": form_data,
            "success": success,
            "error": combined_error,
            "images": images,
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
    badges: List[Dict[str, str]] = []
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
        },
        status_code=status_code,
    )


async def _load_queue_items(include_processed: bool) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    try:
        items = await db.list_work_items(include_processed=include_processed, limit=QUEUE_PAGE_LIMIT)
        return items, None
    except SQLAlchemyError:
        logger.exception("Failed to load work queue")
        return [], "We couldn't load the queue items. Please refresh the page."


async def _render_admin_queue(
    request: Request,
    *,
    show_processed: bool,
    success: Optional[str],
    error: Optional[str],
    status_code: int = status.HTTP_200_OK,
) -> Response:
    queue_items, load_error = await _load_queue_items(show_processed)
    error_messages = [msg for msg in (error, load_error) if msg]
    combined_error = "; ".join(error_messages) if error_messages else None
    return templates.TemplateResponse(
        "admin_queue.html",
        {
            "request": request,
            "queue_items": queue_items,
            "show_processed": show_processed,
            "success": success,
            "error": combined_error,
            "queue_limit": QUEUE_PAGE_LIMIT,
        },
        status_code=status_code,
    )


def _build_queue_redirect(request: Request, params: Dict[str, str]) -> str:
    base_url = str(request.url_for("admin_queue"))
    if params:
        return f"{base_url}?{urlencode(params)}"
    return base_url


@app.get("/id={unique_id}", response_class=HTMLResponse)
async def get_badge(
    request: Request,
    unique_id: str,
    sent: Optional[str] = None,
    error: Optional[str] = None,
) -> Response:
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


@app.post("/id={unique_id}", response_class=HTMLResponse)
async def post_badge(
    request: Request,
    unique_id: str,
    image_label: str = Form(...),
) -> Response:
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


@app.get("/admin/upload", response_class=HTMLResponse)
async def admin_upload_form(
    request: Request,
    image_label: Optional[str] = None,
    success: Optional[str] = None,
    error: Optional[str] = None,
    credentials: HTTPBasicCredentials = Depends(verify_credentials),
) -> Response:
    form_data = {
        "image_label": image_label or "",
    }
    return await _render_admin_upload(
        request,
        form_data,
        success=success,
        error=error,
    )


@app.post("/admin/upload", response_class=HTMLResponse)
async def admin_upload_submit(
    request: Request,
    image_label: str = Form(...),
    image_file: UploadFile = File(...),
    credentials: HTTPBasicCredentials = Depends(verify_credentials),
) -> Response:
    image_label = image_label.strip()
    form_data = {"image_label": image_label}

    if not image_label:
        return await _render_admin_upload(
            request,
            form_data,
            success=None,
            error="Image label is required.",
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
    redirect_url = f"{request.url_for('admin_upload_form')}?{query_params}"
    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/upload/delete", response_class=HTMLResponse)
async def admin_delete_image(
    request: Request,
    image_label: str = Form(...),
    credentials: HTTPBasicCredentials = Depends(verify_credentials),
) -> Response:
    image_label = image_label.strip()
    if not image_label:
        query_params = urlencode({"error": "Image label is required to delete an image."})
        redirect_url = f"{request.url_for('admin_upload_form')}?{query_params}"
        return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    try:
        deleted = await db.delete_available_image(image_label)
    except SQLAlchemyError:
        logger.exception("Failed to delete gallery image %s", image_label)
        return await _render_admin_upload(
            request,
            {"image_label": ""},
            success=None,
            error="Something went wrong while deleting the image. Please try again.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    query_params = (
        {"success": "Badge image deleted successfully."}
        if deleted
        else {"error": "The requested image could not be found."}
    )
    redirect_url = f"{request.url_for('admin_upload_form')}?{urlencode(query_params)}"
    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@app.get("/admin", response_class=HTMLResponse)
async def admin_index(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(verify_credentials),
) -> Response:
    return templates.TemplateResponse(
        "admin_index.html",
        {
            "request": request,
        },
    )


@app.get("/admin/create-badge", response_class=HTMLResponse)
async def admin_create_badge_form(
    request: Request,
    unique_id: Optional[str] = None,
    name: Optional[str] = None,
    edit: Optional[str] = None,
    success: Optional[str] = None,
    error: Optional[str] = None,
    credentials: HTTPBasicCredentials = Depends(verify_credentials),
) -> Response:
    form_data = {
        "unique_id": unique_id or "",
        "name": name or "",
    }
    return await _render_admin_create_badge(
        request,
        form_data,
        success=success,
        error=error,
    )


@app.post("/admin/create-badge", response_class=HTMLResponse)
async def admin_create_badge_submit(
    request: Request,
    unique_id: str = Form(...),
    name: str = Form(...),
    credentials: HTTPBasicCredentials = Depends(verify_credentials),
) -> Response:
    unique_id = unique_id.strip()
    name = name.strip()
    form_data = {"unique_id": unique_id, "name": name}

    if not unique_id or not name:
        return await _render_admin_create_badge(
            request,
            form_data,
            success=None,
            error="Both badge ID and name are required.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        outcome = await db.create_or_update_badge(unique_id=unique_id, name=name)
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
        }
    )
    redirect_url = f"{request.url_for('admin_create_badge_form')}?{query_params}"
    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/api/create-badge", response_class=JSONResponse)
async def admin_create_badge_api(
    payload: Dict[str, Any] = Body(...),
    credentials: HTTPBasicCredentials = Depends(verify_credentials),
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

@app.get("/admin/queue", response_class=HTMLResponse)
async def admin_queue(
    request: Request,
    show_processed: int = 0,
    success: Optional[str] = None,
    error: Optional[str] = None,
    credentials: HTTPBasicCredentials = Depends(verify_credentials),
) -> Response:
    include_processed = bool(show_processed)
    return await _render_admin_queue(
        request,
        show_processed=include_processed,
        success=success,
        error=error,
    )


@app.post("/admin/queue/mark", response_class=HTMLResponse)
async def admin_queue_mark(
    request: Request,
    work_id: int = Form(...),
    show_processed: Optional[str] = Form("0"),
    credentials: HTTPBasicCredentials = Depends(verify_credentials),
) -> Response:
    include_processed = show_processed == "1"
    try:
        result = await db.mark_work_item_processed(work_id)
    except SQLAlchemyError:
        logger.exception("Failed to mark work item %s as processed", work_id)
        return await _render_admin_queue(
            request,
            show_processed=include_processed,
            success=None,
            error="Something went wrong while updating the work item. Please try again.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if result == "marked":
        params: Dict[str, str] = {"success": "Work item marked as processed."}
    elif result == "already_processed":
        params = {"error": "This work item is already marked as processed."}
    else:
        params = {"error": "The requested work item could not be found."}
    if include_processed:
        params["show_processed"] = "1"
    redirect_url = _build_queue_redirect(request, params)
    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/queue/delete", response_class=HTMLResponse)
async def admin_queue_delete(
    request: Request,
    work_id: int = Form(...),
    show_processed: Optional[str] = Form("0"),
    credentials: HTTPBasicCredentials = Depends(verify_credentials),
) -> Response:
    include_processed = show_processed == "1"
    try:
        deleted = await db.delete_work_item(work_id)
    except SQLAlchemyError:
        logger.exception("Failed to delete work item %s", work_id)
        return await _render_admin_queue(
            request,
            show_processed=include_processed,
            success=None,
            error="Something went wrong while deleting the work item. Please try again.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    params: Dict[str, str]
    if deleted:
        params = {"success": "Work item deleted."}
    else:
        params = {"error": "The requested work item could not be found."}
    if include_processed:
        params["show_processed"] = "1"
    redirect_url = _build_queue_redirect(request, params)
    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@app.get("/get-work", response_class=JSONResponse)
async def get_work(
    credentials: HTTPBasicCredentials = Depends(verify_credentials),
) -> Response:
    try:
        work_item = await db.get_oldest_work()
    except SQLAlchemyError:
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
