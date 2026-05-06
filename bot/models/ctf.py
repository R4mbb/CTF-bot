from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base


class CTFStatus(enum.Enum):
    UPCOMING = "upcoming"
    ACTIVE = "active"
    ENDED = "ended"
    ARCHIVED = "archived"


class CTF(Base):
    __tablename__ = "ctfs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ctftime_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[CTFStatus] = mapped_column(
        Enum(CTFStatus), default=CTFStatus.UPCOMING
    )
    visible_after_end: Mapped[bool] = mapped_column(Boolean, default=True)

    # Discord resource IDs
    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    announcement_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Soft delete
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    memberships: Mapped[list["CTFMembership"]] = relationship(back_populates="ctf", cascade="all, delete-orphan")  # noqa: F821
    challenges: Mapped[list["Challenge"]] = relationship(back_populates="ctf", cascade="all, delete-orphan")  # noqa: F821

    @staticmethod
    def _ensure_aware(dt: datetime) -> datetime:
        """SQLite may return naive datetimes; treat them as UTC."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def compute_status(self) -> CTFStatus:
        now = datetime.now(timezone.utc)
        if self.status == CTFStatus.ARCHIVED:
            return CTFStatus.ARCHIVED
        start = self._ensure_aware(self.start_time)
        end = self._ensure_aware(self.end_time)
        if now < start:
            return CTFStatus.UPCOMING
        if now < end:
            return CTFStatus.ACTIVE
        return CTFStatus.ENDED
