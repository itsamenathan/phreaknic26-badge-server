from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import asyncpg

from .config import Settings, get_settings


class Database:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings
        self._pool: Optional[asyncpg.Pool] = None

    def configure(self, settings: Settings) -> None:
        self._settings = settings

    def _require_settings(self) -> Settings:
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    async def connect(self) -> None:
        if self._pool is not None:
            return
        settings = self._require_settings()
        self._pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=settings.pool_min_size,
            max_size=settings.pool_max_size,
        )

    async def disconnect(self) -> None:
        pool, self._pool = self._pool, None
        if pool is not None:
            await pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database pool not initialised")
        return self._pool

    @asynccontextmanager
    async def acquire(self) -> asyncpg.Connection:
        conn = await self.pool.acquire()
        try:
            yield conn
        finally:
            await self.pool.release(conn)

    async def fetch_profile(self, unique_id: str) -> Optional[Dict[str, Any]]:
        async with self.acquire() as conn:
            badge_row = await conn.fetchrow(
                """
                SELECT unique_id, name
                FROM badges
                WHERE unique_id = $1
                """,
                unique_id,
            )
            if badge_row is None:
                return None

            image_rows = await conn.fetch(
                """
                SELECT image_label, image_base64, image_mime_type
                FROM badge_images
                WHERE unique_id = $1
                ORDER BY image_label
                """,
                unique_id,
            )

        images: List[Dict[str, Any]] = [
            {
                "label": row["image_label"],
                "image_base64": row["image_base64"],
                "image_mime_type": row["image_mime_type"],
            }
            for row in image_rows
        ]

        return {
            "unique_id": badge_row["unique_id"],
            "name": badge_row["name"],
            "images": images,
        }

    async def enqueue_selection(
        self,
        unique_id: str,
        name: str,
        image_label: str,
        image_base64: str,
        image_mime_type: Optional[str],
    ) -> None:
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO work_queue (unique_id, name, image_label, image_base64, image_mime_type)
                VALUES ($1, $2, $3, $4, $5)
                """,
                unique_id,
                name,
                image_label,
                image_base64,
                image_mime_type,
            )

    async def get_oldest_work(self) -> Optional[Dict[str, Any]]:
        async with self.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT id, unique_id, name, image_label, image_base64, image_mime_type, created_at
                    FROM work_queue
                    WHERE processed_at IS NULL
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """,
                )
                if row is None:
                    return None

                await conn.execute(
                    "UPDATE work_queue SET processed_at = NOW() WHERE id = $1",
                    row["id"],
                )

        return {
            "unique_id": row["unique_id"],
            "name": row["name"],
            "image_label": row["image_label"],
            "image_base64": row["image_base64"],
             "image_mime_type": row["image_mime_type"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }


db = Database()
