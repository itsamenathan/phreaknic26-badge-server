from __future__ import annotations

import logging
import secrets
from pathlib import Path

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.templating import Jinja2Templates

from .config import get_settings


BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

security = HTTPBasic()
optional_security = HTTPBasic(auto_error=False)
logger = logging.getLogger(__name__)


def _credentials_valid(credentials: Optional[HTTPBasicCredentials]) -> bool:
    if credentials is None:
        return False

    settings = get_settings()
    correct_username = secrets.compare_digest(
        credentials.username or "",
        settings.basic_auth_username,
    )
    correct_password = secrets.compare_digest(
        credentials.password or "",
        settings.basic_auth_password,
    )
    return correct_username and correct_password


def verify_credentials(
    credentials: HTTPBasicCredentials = Depends(security),
) -> HTTPBasicCredentials:
    if not _credentials_valid(credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials


def is_admin_user(
    credentials: Optional[HTTPBasicCredentials] = Depends(optional_security),
) -> bool:
    return _credentials_valid(credentials)
