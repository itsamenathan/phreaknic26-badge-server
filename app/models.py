from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarative class for SQLAlchemy models."""


class Badge(Base):
    __tablename__ = "badges"

    unique_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(Text)

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


class AvailableImage(Base):
    __tablename__ = "available_images"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    image_label: Mapped[str] = mapped_column(String, unique=True)
    image_base64: Mapped[str] = mapped_column(Text)
    image_mime_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class WorkQueue(Base):
    __tablename__ = "work_queue"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    unique_id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(Text)
    image_label: Mapped[str] = mapped_column(String)
    image_base64: Mapped[str] = mapped_column(Text)
    image_mime_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
