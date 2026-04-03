from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.audit import AuditLog

logger = logging.getLogger(__name__)


async def log_action(
    session: AsyncSession,
    guild_id: int,
    user_id: int,
    action: str,
    detail: str | None = None,
) -> None:
    """Write an audit log entry using the caller's existing session."""
    entry = AuditLog(
        guild_id=guild_id,
        user_id=user_id,
        action=action,
        detail=detail,
    )
    session.add(entry)
    logger.info("Audit: guild=%s user=%s action=%s detail=%s", guild_id, user_id, action, detail)
