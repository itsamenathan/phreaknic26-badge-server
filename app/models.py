from __future__ import annotations

from typing import List, Optional

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .constants import DEFAULT_IMAGE_COLOR, DEFAULT_IMAGE_FONT


class Base(DeclarativeBase):
    """Base declarative class for SQLAlchemy models."""


class Badge(Base):
    __tablename__ = "badges"

    unique_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    mac_address: Mapped[Optional[str]] = mapped_column(
        String(17),
        unique=True,
        nullable=True,
    )
    firmware_base64: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    firmware_hash: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    selected_image_label: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    selected_image_base64: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    selected_image_mime_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    selected_image_color: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    selected_image_font: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    selected_font_size: Mapped[Optional[int]] = mapped_column(nullable=True)
    selected_text_x: Mapped[Optional[int]] = mapped_column(nullable=True)
    selected_text_y: Mapped[Optional[int]] = mapped_column(nullable=True)

    images: Mapped[List["BadgeImage"]] = relationship(
        back_populates="badge",
        order_by="BadgeImage.image_label",
        cascade="all, delete-orphan",
    )


class BadgeImage(Base):
    __tablename__ = "badge_images"

    unique_id: Mapped[str] = mapped_column(
        ForeignKey("badges.unique_id", ondelete="CASCADE"),
        primary_key=True,
    )
    image_label: Mapped[str] = mapped_column(String, primary_key=True)
    image_base64: Mapped[str] = mapped_column(Text)
    image_mime_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    badge: Mapped[Badge] = relationship(back_populates="images")


class BadgeUnlockedImage(Base):
    __tablename__ = "badge_unlocked_images"

    unique_id: Mapped[str] = mapped_column(
        ForeignKey("badges.unique_id", ondelete="CASCADE"),
        primary_key=True,
    )
    image_label: Mapped[str] = mapped_column(String, primary_key=True)


class AvailableImage(Base):
    __tablename__ = "available_images"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    image_label: Mapped[str] = mapped_column(String, unique=True)
    requires_secret_code: Mapped[bool] = mapped_column(nullable=False, default=True)
    secret_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    image_base64: Mapped[str] = mapped_column(Text)
    image_mime_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    image_color: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=DEFAULT_IMAGE_COLOR,
    )
    image_font: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=DEFAULT_IMAGE_FONT,
    )
    display_order: Mapped[int] = mapped_column(nullable=False, default=0)
