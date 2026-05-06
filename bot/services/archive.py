"""Shared CTF archive flow.

Used by both the auto-archive scheduler and the manual /end_ctf admin command,
so the side effects (leaderboard post, end-report post, role release, read-only
lockdown) are identical regardless of how the CTF is wound down.
"""
from __future__ import annotations

import logging
from collections import defaultdict

import discord
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.ctf import CTF, CTFStatus
from bot.services.ctf_service import (
    get_achievements,
    get_leaderboard,
    get_member_count,
    list_challenges,
)
from bot.services.discord_service import (
    delete_ctf_role,
    get_channel_by_name,
    get_team_role,
    make_category_public,
)
from bot.utils.embeds import ctf_end_report_embed, leaderboard_embed

logger = logging.getLogger(__name__)


async def _post_leaderboard(
    ctf: CTF,
    category: discord.CategoryChannel,
    session: AsyncSession,
) -> None:
    """Post the live leaderboard to #scoreboard before the CTF locks."""
    sb_ch = get_channel_by_name(category, "scoreboard")
    if sb_ch is None:
        logger.info("CTF '%s' has no #scoreboard channel; skipping leaderboard post", ctf.name)
        return
    try:
        rows = await get_leaderboard(session, ctf.id)
        member_count = await get_member_count(session, ctf.id)
        achievements = await get_achievements(session, ctf.id)
        embed = leaderboard_embed(
            ctf.name, rows, member_count=member_count, achievements=achievements,
        )
        await sb_ch.send(embed=embed)
        logger.info("Posted final leaderboard for CTF '%s' to #%s", ctf.name, sb_ch.name)
    except discord.HTTPException as exc:
        logger.warning("Failed to post leaderboard for CTF '%s': %s", ctf.name, exc)


async def _post_end_report(
    ctf: CTF,
    category: discord.CategoryChannel,
    session: AsyncSession,
) -> None:
    """Post a summary embed to the CTF's #announcements channel."""
    announce = get_channel_by_name(category, "announcements")
    if announce is None:
        logger.info("CTF '%s' has no #announcements channel; skipping end report", ctf.name)
        return
    try:
        challenges = await list_challenges(session, ctf.id)
        leaderboard = await get_leaderboard(session, ctf.id)
        member_count = await get_member_count(session, ctf.id)

        by_cat: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [solved, total]
        for c in challenges:
            stats = by_cat[c.category]
            stats[1] += 1
            if c.solved:
                stats[0] += 1
        by_category = [(cat, s, t) for cat, (s, t) in by_cat.items()]

        top_solvers = [(uid, solves) for uid, solves, _ in leaderboard[:3]]
        solved_count = sum(1 for c in challenges if c.solved)

        embed = ctf_end_report_embed(
            ctf,
            total_challenges=len(challenges),
            solved_count=solved_count,
            by_category=by_category,
            top_solvers=top_solvers,
            member_count=member_count,
        )
        await announce.send(embed=embed)
        logger.info("Posted end report for CTF '%s' to #%s", ctf.name, announce.name)
    except discord.HTTPException as exc:
        logger.warning("Failed to post end report for CTF '%s': %s", ctf.name, exc)


async def archive_ctf(
    ctf: CTF,
    guild: discord.Guild,
    session: AsyncSession,
    *,
    team_role_name: str,
    reason: str = "auto-archive",
) -> bool:
    """Run the full archive sequence for a CTF.

    Steps (each isolated so a single failure doesn't abort the rest):
      1. Post the final leaderboard to ``#scoreboard``.
      2. Post the end report to ``#announcements``.
      3. Delete the per-CTF role (auto-removes it from every participant).
      4. Lock the category read-only via ``team_role`` overwrite.
      5. Mark the CTF row as ``ARCHIVED`` and clear ``role_id``.

    Returns True if the category resolved and lockdown ran. Returns False when
    the CTF has no category at all (in which case it's still flipped to
    ARCHIVED so the scheduler doesn't keep retrying it).
    """
    if not ctf.category_id:
        logger.warning("CTF '%s' (id=%d) has no category_id; marking ARCHIVED only", ctf.name, ctf.id)
        ctf.status = CTFStatus.ARCHIVED
        return False

    category = guild.get_channel(ctf.category_id)
    if not isinstance(category, discord.CategoryChannel):
        logger.warning("Category %d not found for CTF '%s'; marking ARCHIVED only", ctf.category_id, ctf.name)
        ctf.status = CTFStatus.ARCHIVED
        return False

    await _post_leaderboard(ctf, category, session)
    await _post_end_report(ctf, category, session)

    team_role = get_team_role(guild, team_role_name)
    stored_role_id = ctf.role_id
    if stored_role_id:
        await delete_ctf_role(guild, stored_role_id)
        ctf.role_id = None

    try:
        await make_category_public(category, guild, team_role=team_role, ctf_role=None)
    except discord.HTTPException as exc:
        logger.error("Failed to lock category for CTF '%s' (%s): %s", ctf.name, reason, exc)

    ctf.status = CTFStatus.ARCHIVED
    logger.info("Archived CTF '%s' in guild %d (%s)", ctf.name, ctf.guild_id, reason)
    return True
