"""Live updates to the per-CTF announcement embed (participant counter)."""
from __future__ import annotations

import logging

import discord
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.ctf import CTF
from bot.services.ctf_service import get_member_count
from bot.services.discord_service import get_channel_by_name
from bot.utils.embeds import ctf_announcement_embed

logger = logging.getLogger(__name__)


async def refresh_announcement_member_count(
    guild: discord.Guild, ctf: CTF, session: AsyncSession
) -> None:
    """Edit the CTF's announcement message in place to show the current count.

    Silently no-ops on missing/deleted prerequisites (no announcement message,
    category gone, message deleted manually). Anything that goes wrong is
    logged at debug/warning so the calling join/leave path always succeeds —
    a stale counter must never block the actual join action.
    """
    if not ctf.announcement_message_id or not ctf.category_id:
        return

    category = guild.get_channel(ctf.category_id)
    if not isinstance(category, discord.CategoryChannel):
        return

    announce_ch = get_channel_by_name(category, "announcements")
    if announce_ch is None:
        return

    try:
        msg = await announce_ch.fetch_message(ctf.announcement_message_id)
    except discord.NotFound:
        logger.debug("Announcement message for CTF '%s' was deleted; skipping refresh", ctf.name)
        return
    except discord.Forbidden:
        logger.warning("Bot lacks read access to announcement message for CTF '%s'", ctf.name)
        return
    except discord.HTTPException as exc:
        logger.warning("Failed to fetch announcement for CTF '%s': %s", ctf.name, exc)
        return

    member_count = await get_member_count(session, ctf.id)
    embed = ctf_announcement_embed(ctf, member_count=member_count)

    try:
        await msg.edit(embed=embed)
    except discord.HTTPException as exc:
        logger.warning("Failed to refresh announcement counter for CTF '%s': %s", ctf.name, exc)
