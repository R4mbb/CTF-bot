from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base


class ChallengeSolve(Base):
    __tablename__ = "challenge_solves"
    __table_args__ = (
        # A given user can claim a given challenge at most once. Prevents
        # double-counting from network retries / double-click / concurrent
        # /solve_challenge calls. Different users can each have their own row
        # for the same challenge — that's the team-CTF model the leaderboard
        # is built for.
        UniqueConstraint("challenge_id", "user_id", name="uq_solve_user_challenge"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger)
    flag: Mapped[str | None] = mapped_column(String(500), nullable=True)
    writeup_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    solved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    challenge: Mapped["Challenge"] = relationship(back_populates="solves")  # noqa: F821
