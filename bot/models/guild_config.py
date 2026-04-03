from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base


class GuildConfig(Base):
    __tablename__ = "guild_configs"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    admin_role_name: Mapped[str] = mapped_column(String(100), default="CTF Admin")
    archive_category_name: Mapped[str] = mapped_column(String(100), default="CTF Archive")
    log_channel_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
