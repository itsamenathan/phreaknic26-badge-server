from __future__ import annotations

from dataclasses import dataclass
import os
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    database_url: str
    basic_auth_username: str
    basic_auth_password: str
    pool_min_size: int = 1
    pool_max_size: int = 10


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    database_url = os.environ.get("DATABASE_URL")
    basic_auth_username = os.environ.get("WORK_BASIC_AUTH_USERNAME")
    basic_auth_password = os.environ.get("WORK_BASIC_AUTH_PASSWORD")

    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")
    if not basic_auth_username or not basic_auth_password:
        raise RuntimeError(
            "WORK_BASIC_AUTH_USERNAME and WORK_BASIC_AUTH_PASSWORD environment variables are required",
        )

    pool_min_size = int(os.environ.get("DB_POOL_MIN_SIZE", "1"))
    pool_max_size = int(os.environ.get("DB_POOL_MAX_SIZE", "10"))

    return Settings(
        database_url=database_url,
        basic_auth_username=basic_auth_username,
        basic_auth_password=basic_auth_password,
        pool_min_size=pool_min_size,
        pool_max_size=pool_max_size,
    )
