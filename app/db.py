from __future__ import annotations

import base64
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Set, Tuple

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import Settings, get_settings
from .constants import DEFAULT_IMAGE_COLOR, DEFAULT_IMAGE_FONT
from .models import AvailableImage, Badge, BadgeImage, BadgeUnlockedImage, Base


DEFAULT_FIRMWARE_PATH = (
    Path(__file__).resolve().parent / "static" / "firmware" / "default.bin"
)

_DEFAULT_FIRMWARE_CACHE: Optional[Tuple[str, str]] = None


def _calculate_default_firmware_hash(firmware_bytes: bytes) -> str:
    return "0" * 16


def _load_default_firmware_payload() -> Tuple[str, str]:
    global _DEFAULT_FIRMWARE_CACHE
    if _DEFAULT_FIRMWARE_CACHE is None:
        firmware_bytes = DEFAULT_FIRMWARE_PATH.read_bytes()
        firmware_base64 = base64.b64encode(firmware_bytes).decode("ascii")
        firmware_hash = _calculate_default_firmware_hash(firmware_bytes)
        _DEFAULT_FIRMWARE_CACHE = (firmware_base64, firmware_hash)
    return _DEFAULT_FIRMWARE_CACHE


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

            image_stmt = select(AvailableImage).order_by(
                AvailableImage.display_order.asc(),
                AvailableImage.image_label.asc(),
            )
            image_rows = await session.scalars(image_stmt)
            unlocked_stmt = select(BadgeUnlockedImage.image_label).where(
                BadgeUnlockedImage.unique_id == unique_id
            )
            unlocked_rows = await session.scalars(unlocked_stmt)
            unlocked_labels: Set[str] = set(unlocked_rows.all())

            images: List[Dict[str, Any]] = []
            for image in image_rows:
                label = image.image_label
                is_unlocked = label in unlocked_labels
                images.append(
                    {
                        "label": label,
                        "image_base64": image.image_base64,
                        "image_mime_type": image.image_mime_type,
                        "image_color": image.image_color or DEFAULT_IMAGE_COLOR,
                        "image_font": image.image_font or DEFAULT_IMAGE_FONT,
                        "requires_secret_code": bool(image.requires_secret_code),
                        "display_order": image.display_order or 0,
                        "is_unlocked": is_unlocked,
                    }
                )

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

    async def get_badge_by_unique_id(
        self,
        unique_id: str,
    ) -> Optional[Dict[str, Any]]:
        async with self.session() as session:
            stmt = select(Badge).where(Badge.unique_id == unique_id)
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
        secret_code: Optional[str],
        requires_secret_code: bool,
        display_order: int,
    ) -> bool:
        async with self.session() as session:
            stmt = select(AvailableImage).where(AvailableImage.image_label == image_label)
            gallery_image = await session.scalar(stmt)
            created = False
            if gallery_image is None:
                gallery_image = AvailableImage(
                    image_label=image_label,
                    requires_secret_code=requires_secret_code,
                    secret_code=secret_code,
                    image_base64=image_base64,
                    image_mime_type=image_mime_type,
                    image_color=image_color or DEFAULT_IMAGE_COLOR,
                    image_font=image_font or DEFAULT_IMAGE_FONT,
                    display_order=display_order,
                )
                session.add(gallery_image)
                created = True
            else:
                gallery_image.requires_secret_code = requires_secret_code
                gallery_image.secret_code = secret_code
                gallery_image.image_base64 = image_base64
                gallery_image.image_mime_type = image_mime_type
                gallery_image.image_color = image_color or DEFAULT_IMAGE_COLOR
                gallery_image.image_font = image_font or DEFAULT_IMAGE_FONT
                gallery_image.display_order = display_order

        return created

    async def list_available_images(self) -> List[Dict[str, Any]]:
        async with self.session() as session:
            stmt = select(AvailableImage).order_by(
                AvailableImage.display_order.asc(),
                AvailableImage.image_label.asc(),
            )
            result = await session.scalars(stmt)
            images = result.all()

        return [
            {
                "image_label": image.image_label,
                "requires_secret_code": bool(image.requires_secret_code),
                "secret_code": image.secret_code,
                "image_base64": image.image_base64,
                "image_mime_type": image.image_mime_type,
                "image_color": image.image_color or DEFAULT_IMAGE_COLOR,
                "image_font": image.image_font or DEFAULT_IMAGE_FONT,
                "display_order": image.display_order or 0,
            }
            for image in images
        ]

    async def fetch_available_image(self, image_label: str) -> Optional[Dict[str, Any]]:
        async with self.session() as session:
            stmt = select(AvailableImage).where(AvailableImage.image_label == image_label)
            image = await session.scalar(stmt)

        if image is None:
            return None

        return {
            "image_label": image.image_label,
            "requires_secret_code": bool(image.requires_secret_code),
            "secret_code": image.secret_code,
            "image_base64": image.image_base64,
            "image_mime_type": image.image_mime_type,
            "image_color": image.image_color or DEFAULT_IMAGE_COLOR,
            "image_font": image.image_font or DEFAULT_IMAGE_FONT,
        }

    async def fetch_available_image_by_code(self, secret_code: str) -> Optional[Dict[str, Any]]:
        cleaned_code = (secret_code or "").strip().casefold()
        if not cleaned_code:
            return None

        async with self.session() as session:
            stmt = select(AvailableImage).where(
                func.lower(AvailableImage.secret_code) == cleaned_code
            )
            image = await session.scalar(stmt)

        if image is None:
            return None

        return {
            "image_label": image.image_label,
            "requires_secret_code": bool(image.requires_secret_code),
            "secret_code": image.secret_code,
            "image_base64": image.image_base64,
            "image_mime_type": image.image_mime_type,
            "image_color": image.image_color or DEFAULT_IMAGE_COLOR,
            "image_font": image.image_font or DEFAULT_IMAGE_FONT,
            "display_order": image.display_order or 0,
        }

    async def update_available_image_metadata(
        self,
        image_label: str,
        *,
        image_color: str,
        image_font: str,
        secret_code: Optional[str],
        requires_secret_code: bool,
        display_order: int,
    ) -> bool:
        async with self.session() as session:
            image = await session.scalar(
                select(AvailableImage).where(AvailableImage.image_label == image_label)
            )
            if image is None:
                return False

            image.image_color = image_color or DEFAULT_IMAGE_COLOR
            image.image_font = image_font or DEFAULT_IMAGE_FONT
            image.secret_code = secret_code
            image.requires_secret_code = requires_secret_code
            image.display_order = display_order

        return True

    async def mark_image_unlocked(self, unique_id: str, image_label: str) -> bool:
        async with self.session() as session:
            badge = await session.scalar(select(Badge).where(Badge.unique_id == unique_id))
            if badge is None:
                return False

            existing = await session.scalar(
                select(BadgeUnlockedImage).where(
                    BadgeUnlockedImage.unique_id == unique_id,
                    BadgeUnlockedImage.image_label == image_label,
                )
            )
            if existing is not None:
                return True

            unlocked = BadgeUnlockedImage(unique_id=unique_id, image_label=image_label)
            session.add(unlocked)

        return True

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
                firmware_base64, firmware_hash = _load_default_firmware_payload()
                badge = Badge(
                    unique_id=unique_id,
                    name=name,
                    mac_address=mac_address,
                    firmware_base64=firmware_base64,
                    firmware_hash=firmware_hash,
                )
                session.add(badge)
                return "created"

            badge.name = name
            badge.mac_address = mac_address
            return "updated"

    async def update_badge_unique_id(self, current_id: str, new_id: str) -> str:
        async with self.session() as session:
            badge = await session.scalar(select(Badge).where(Badge.unique_id == current_id))
            if badge is None:
                return "not_found"
            if current_id == new_id:
                return "unchanged"
            existing = await session.scalar(select(Badge).where(Badge.unique_id == new_id))
            if existing is not None:
                return "conflict"

            await session.execute(
                update(BadgeImage).where(BadgeImage.unique_id == current_id).values(unique_id=new_id)
            )
            await session.execute(
                update(BadgeUnlockedImage)
                .where(BadgeUnlockedImage.unique_id == current_id)
                .values(unique_id=new_id)
            )
            badge.unique_id = new_id
        return "updated"

    async def update_badge_name(self, unique_id: str, name: str) -> bool:
        async with self.session() as session:
            stmt = select(Badge).where(Badge.unique_id == unique_id)
            badge = await session.scalar(stmt)
            if badge is None:
                return False

            badge.name = name

        return True

    async def delete_badge(self, unique_id: str) -> bool:
        async with self.session() as session:
            badge = await session.scalar(select(Badge).where(Badge.unique_id == unique_id))
            if badge is None:
                return False
            await session.delete(badge)
        return True

    async def list_badges(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        async with self.session() as session:
            stmt = select(Badge).order_by(Badge.unique_id.asc())
            if limit is not None:
                stmt = stmt.limit(limit)
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
