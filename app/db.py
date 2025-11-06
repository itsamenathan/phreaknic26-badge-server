from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import Settings, get_settings
from .constants import DEFAULT_IMAGE_COLOR, DEFAULT_IMAGE_FONT
from .models import AvailableImage, Badge, Base


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
                    "image_color": image.image_color or DEFAULT_IMAGE_COLOR,
                    "image_font": image.image_font or DEFAULT_IMAGE_FONT,
                }
                for image in image_rows
            ]

            return {
                "unique_id": badge.unique_id,
                "name": badge.name,
                "mac_address": badge.mac_address,
                "firmware_base64": badge.firmware_base64,
                "firmware_hash": badge.firmware_hash,
                "selected_image_label": badge.selected_image_label,
                "selected_image_base64": badge.selected_image_base64,
                "selected_image_mime_type": badge.selected_image_mime_type,
                "selected_image_color": badge.selected_image_color,
                "selected_image_font": badge.selected_image_font,
                "selected_font_size": badge.selected_font_size,
                "selected_text_x": badge.selected_text_x,
                "selected_text_y": badge.selected_text_y,
                "images": images,
            }

    async def get_badge_by_mac(self, mac_address: str) -> Optional[Dict[str, Any]]:
        async with self.session() as session:
            stmt = select(Badge).where(Badge.mac_address == mac_address)
            badge = await session.scalar(stmt)
            if badge is None:
                return None

            return {
                "unique_id": badge.unique_id,
                "name": badge.name,
                "mac_address": badge.mac_address,
                "firmware_base64": badge.firmware_base64,
                "firmware_hash": badge.firmware_hash,
                "selected_image_label": badge.selected_image_label,
                "selected_image_base64": badge.selected_image_base64,
                "selected_image_mime_type": badge.selected_image_mime_type,
                "selected_image_color": badge.selected_image_color,
                "selected_image_font": badge.selected_image_font,
                "selected_font_size": badge.selected_font_size,
                "selected_text_x": badge.selected_text_x,
                "selected_text_y": badge.selected_text_y,
            }

    async def save_badge_render(
        self,
        unique_id: str,
        *,
        image_label: str,
        image_base64: str,
        image_mime_type: Optional[str],
        image_color: str,
        image_font: str,
        font_size: Optional[int],
        text_x: Optional[int],
        text_y: Optional[int],
        firmware_base64: str,
        firmware_hash: str,
    ) -> bool:
        async with self.session() as session:
            stmt = select(Badge).where(Badge.unique_id == unique_id)
            badge = await session.scalar(stmt)
            if badge is None:
                return False

            badge.selected_image_label = image_label
            badge.selected_image_base64 = image_base64
            badge.selected_image_mime_type = image_mime_type
            badge.selected_image_color = image_color
            badge.selected_image_font = image_font
            badge.selected_font_size = font_size
            badge.selected_text_x = text_x
            badge.selected_text_y = text_y
            badge.firmware_base64 = firmware_base64
            badge.firmware_hash = firmware_hash
        return True

    async def store_available_image(
        self,
        image_label: str,
        image_base64: str,
        image_mime_type: Optional[str],
        image_color: str,
        image_font: str,
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
                    image_color=image_color or DEFAULT_IMAGE_COLOR,
                    image_font=image_font or DEFAULT_IMAGE_FONT,
                )
                session.add(gallery_image)
                created = True
            else:
                gallery_image.image_base64 = image_base64
                gallery_image.image_mime_type = image_mime_type
                gallery_image.image_color = image_color or DEFAULT_IMAGE_COLOR
                gallery_image.image_font = image_font or DEFAULT_IMAGE_FONT

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
                "image_color": image.image_color or DEFAULT_IMAGE_COLOR,
                "image_font": image.image_font or DEFAULT_IMAGE_FONT,
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

    async def create_or_update_badge(self, unique_id: str, name: str, mac_address: Optional[str]) -> str:
        async with self.session() as session:
            stmt = select(Badge).where(Badge.unique_id == unique_id)
            badge = await session.scalar(stmt)
            if badge is None:
                badge = Badge(unique_id=unique_id, name=name, mac_address=mac_address)
                session.add(badge)
                return "created"

            badge.name = name
            badge.mac_address = mac_address
            return "updated"

    async def update_badge_name(self, unique_id: str, name: str) -> bool:
        async with self.session() as session:
            stmt = select(Badge).where(Badge.unique_id == unique_id)
            badge = await session.scalar(stmt)
            if badge is None:
                return False

            badge.name = name

        return True

    async def list_badges(self, limit: int = 100) -> List[Dict[str, Any]]:
        async with self.session() as session:
            stmt = select(Badge).order_by(Badge.unique_id.asc()).limit(limit)
            rows = await session.scalars(stmt)
            badges = rows.all()

        results: List[Dict[str, Any]] = []
        for badge in badges:
            image_base64 = badge.selected_image_base64 or ""
            image_mime = badge.selected_image_mime_type or "image/png"
            image_data_uri = None
            if image_base64:
                image_data_uri = f"data:{image_mime};base64,{image_base64}"
            results.append(
                {
                    "unique_id": badge.unique_id,
                    "name": badge.name,
                    "mac_address": badge.mac_address,
                    "firmware_base64": badge.firmware_base64,
                    "firmware_hash": badge.firmware_hash,
                    "selected_image_label": badge.selected_image_label,
                    "selected_image_base64": image_base64,
                    "selected_image_mime_type": badge.selected_image_mime_type,
                    "selected_image_color": badge.selected_image_color,
                    "selected_image_font": badge.selected_image_font,
                    "selected_font_size": badge.selected_font_size,
                    "selected_text_x": badge.selected_text_x,
                    "selected_text_y": badge.selected_text_y,
                    "selected_image_data_uri": image_data_uri,
                }
            )
        return results

db = Database()
