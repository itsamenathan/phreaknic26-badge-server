from __future__ import annotations

import logging
import secrets
from pathlib import Path

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.templating import Jinja2Templates

from .config import get_settings


BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

security = HTTPBasic()
logger = logging.getLogger(__name__)


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
