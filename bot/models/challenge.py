from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base


class Challenge(Base):
    __tablename__ = "challenges"
    __table_args__ = (
        UniqueConstraint("ctf_id", "category", "name", name="uq_ctf_challenge"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ctf_id: Mapped[int] = mapped_column(ForeignKey("ctfs.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    challenge_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_by: Mapped[int] = mapped_column(BigInteger)
    solved: Mapped[bool] = mapped_column(default=False)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    ctf: Mapped["CTF"] = relationship(back_populates="challenges")  # noqa: F821
    solves: Mapped[list["ChallengeSolve"]] = relationship(back_populates="challenge", cascade="all, delete-orphan")  # noqa: F821
