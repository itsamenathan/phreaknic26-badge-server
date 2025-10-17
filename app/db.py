from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import Settings, get_settings
from .models import AvailableImage, Badge, Base, WorkQueue


class Database:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    def configure(self, settings: Settings) -> None:
        self._settings = settings

    def _require_settings(self) -> Settings:
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    @staticmethod
    def _normalise_database_url(url: str) -> str:
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    async def connect(self) -> None:
        if self._engine is not None:
            return

        settings = self._require_settings()
        database_url = self._normalise_database_url(settings.database_url)

        pool_size = max(settings.pool_min_size, 1)
        max_overflow = max(settings.pool_max_size - pool_size, 0)

        self._engine = create_async_engine(
            database_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
        )

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
        )

    async def disconnect(self) -> None:
        engine, self._engine = self._engine, None
        self._session_factory = None
        if engine is not None:
            await engine.dispose()

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            raise RuntimeError("Database engine not initialised")
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            raise RuntimeError("Session factory not initialised")
        return self._session_factory

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def fetch_profile(self, unique_id: str) -> Optional[Dict[str, Any]]:
        async with self.session() as session:
            badge_stmt = select(Badge).where(Badge.unique_id == unique_id)
            badge = await session.scalar(badge_stmt)
            if badge is None:
                return None

            image_stmt = select(AvailableImage).order_by(AvailableImage.image_label)
            image_rows = await session.scalars(image_stmt)
            images: List[Dict[str, Any]] = [
                {
                    "label": image.image_label,
                    "image_base64": image.image_base64,
                    "image_mime_type": image.image_mime_type,
                }
                for image in image_rows
            ]

            return {
                "unique_id": badge.unique_id,
                "name": badge.name,
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
        async with self.session() as session:
            work_item = WorkQueue(
                unique_id=unique_id,
                name=name,
                image_label=image_label,
                image_base64=image_base64,
                image_mime_type=image_mime_type,
            )
            session.add(work_item)

    async def store_available_image(
        self,
        image_label: str,
        image_base64: str,
        image_mime_type: Optional[str],
    ) -> bool:
        async with self.session() as session:
            stmt = select(AvailableImage).where(AvailableImage.image_label == image_label)
            gallery_image = await session.scalar(stmt)
            created = False
            if gallery_image is None:
                gallery_image = AvailableImage(
                    image_label=image_label,
                    image_base64=image_base64,
                    image_mime_type=image_mime_type,
                )
                session.add(gallery_image)
                created = True
            else:
                gallery_image.image_base64 = image_base64
                gallery_image.image_mime_type = image_mime_type

        return created

    async def list_available_images(self) -> List[Dict[str, Any]]:
        async with self.session() as session:
            stmt = select(AvailableImage).order_by(AvailableImage.image_label.asc())
            result = await session.scalars(stmt)
            images = result.all()

        return [
            {
                "image_label": image.image_label,
                "image_base64": image.image_base64,
                "image_mime_type": image.image_mime_type,
            }
            for image in images
        ]

    async def delete_available_image(self, image_label: str) -> bool:
        async with self.session() as session:
            stmt = select(AvailableImage).where(AvailableImage.image_label == image_label)
            gallery_image = await session.scalar(stmt)
            if gallery_image is None:
                return False

            await session.delete(gallery_image)

        return True

    async def create_or_update_badge(self, unique_id: str, name: str) -> str:
        async with self.session() as session:
            stmt = select(Badge).where(Badge.unique_id == unique_id)
            badge = await session.scalar(stmt)
            if badge is None:
                badge = Badge(unique_id=unique_id, name=name)
                session.add(badge)
                return "created"

            badge.name = name
            return "updated"

    async def list_badges(self, limit: int = 100) -> List[Dict[str, Any]]:
        async with self.session() as session:
            stmt = select(Badge).order_by(Badge.unique_id.asc()).limit(limit)
            rows = await session.scalars(stmt)
            badges = rows.all()

        return [
            {
                "unique_id": badge.unique_id,
                "name": badge.name,
            }
            for badge in badges
        ]

    async def list_work_items(
        self,
        *,
        include_processed: bool = False,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        async with self.session() as session:
            stmt = select(WorkQueue).order_by(WorkQueue.created_at.desc())
            if not include_processed:
                stmt = stmt.where(WorkQueue.processed_at.is_(None))
            stmt = stmt.limit(limit)
            result = await session.scalars(stmt)
            items = result.all()

        work_items: List[Dict[str, Any]] = []
        for item in items:
            mime_type = item.image_mime_type or "image/png"
            work_items.append(
                {
                    "id": item.id,
                    "unique_id": item.unique_id,
                    "name": item.name,
                    "image_label": item.image_label,
                    "image_mime_type": mime_type,
                    "image_base64": item.image_base64,
                    "image_data_uri": f"data:{mime_type};base64,{item.image_base64}",
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "processed_at": item.processed_at.isoformat() if item.processed_at else None,
                    "is_processed": item.processed_at is not None,
                }
            )

        return work_items

    async def mark_work_item_processed(self, work_id: int) -> str:
        async with self.session() as session:
            stmt = select(WorkQueue).where(WorkQueue.id == work_id)
            work_item = await session.scalar(stmt)
            if work_item is None:
                return "not_found"
            if work_item.processed_at is not None:
                return "already_processed"

            work_item.processed_at = datetime.now(timezone.utc)

        return "marked"

    async def delete_work_item(self, work_id: int) -> bool:
        async with self.session() as session:
            stmt = select(WorkQueue).where(WorkQueue.id == work_id)
            work_item = await session.scalar(stmt)
            if work_item is None:
                return False

            await session.delete(work_item)

        return True

    async def get_oldest_work(self) -> Optional[Dict[str, Any]]:
        async with self.session() as session:
            stmt = (
                select(WorkQueue)
                .where(WorkQueue.processed_at.is_(None))
                .order_by(WorkQueue.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            work = await session.scalar(stmt)
            if work is None:
                return None

            work.processed_at = datetime.now(timezone.utc)
            await session.flush()

            return {
                "unique_id": work.unique_id,
                "name": work.name,
                "image_label": work.image_label,
                "image_base64": work.image_base64,
                "image_mime_type": work.image_mime_type,
                "created_at": work.created_at.isoformat() if work.created_at else None,
            }


db = Database()
