from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base


class CTFMembership(Base):
    __tablename__ = "ctf_memberships"
    __table_args__ = (
        UniqueConstraint("ctf_id", "user_id", name="uq_ctf_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ctf_id: Mapped[int] = mapped_column(ForeignKey("ctfs.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger)
    guild_id: Mapped[int] = mapped_column(BigInteger)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    ctf: Mapped["CTF"] = relationship(back_populates="memberships")  # noqa: F821
