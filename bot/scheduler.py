"""Background scheduler for CTF lifecycle management and weekly announcements."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.db import get_session
from bot.integrations.ctftime import CTFTimeClient
from bot.models.ctf import CTF, CTFStatus
from bot.services.ctf_service import get_ended_ctfs_needing_archive
from bot.services.discord_service import make_category_public
from bot.services.discord_log import send_log
from bot.utils.embeds import ctftime_events_embed

logger = logging.getLogger(__name__)


class CTFScheduler:
    def __init__(
        self,
        bot: discord.Client,
        interval_minutes: int = 5,
        announcement_channel: str | None = None,
        ctftime_cache_ttl: int = 1800,
    ):
        self._bot = bot
        self._scheduler = AsyncIOScheduler()
        self._interval = interval_minutes
        self._announcement_channel = announcement_channel
        self._ctftime_client = CTFTimeClient(cache_ttl=ctftime_cache_ttl)

    def start(self) -> None:
        self._scheduler.add_job(
            self._check_ctf_lifecycle,
            "interval",
            minutes=self._interval,
            id="ctf_lifecycle",
            replace_existing=True,
        )

        # Weekly CTFTime announcement: Monday 09:00 KST = Monday 00:00 UTC
        if self._announcement_channel:
            self._scheduler.add_job(
                self._weekly_ctftime_announcement,
                CronTrigger(day_of_week="mon", hour=0, minute=0, timezone="UTC"),
                id="weekly_ctftime",
                replace_existing=True,
            )
            logger.info(
                "Weekly CTFTime announcement scheduled (Mon 09:00 KST) -> #%s",
                self._announcement_channel,
            )

        self._scheduler.start()
        logger.info("Scheduler started (lifecycle interval=%d min)", self._interval)

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    # ── CTF Lifecycle ─────────────────────────────────────────────────────

    async def _check_ctf_lifecycle(self) -> None:
        logger.debug("Running CTF lifecycle check")
        try:
            async with get_session() as session:
                ctfs = await get_ended_ctfs_needing_archive(session)
                for ctf in ctfs:
                    await self._archive_ctf(ctf, session)
        except Exception:
            logger.exception("Error in CTF lifecycle check")

    async def _archive_ctf(self, ctf: CTF, session) -> None:
        if not ctf.category_id:
            logger.warning("CTF '%s' (id=%d) has no category_id, skipping archive", ctf.name, ctf.id)
            ctf.status = CTFStatus.ARCHIVED
            return

        guild = self._bot.get_guild(ctf.guild_id)
        if not guild:
            logger.warning("Guild %d not found for CTF '%s'", ctf.guild_id, ctf.name)
            return

        category = guild.get_channel(ctf.category_id)
        if not isinstance(category, discord.CategoryChannel):
            logger.warning("Category %d not found for CTF '%s'", ctf.category_id, ctf.name)
            ctf.status = CTFStatus.ARCHIVED
            return

        try:
            await make_category_public(category, guild)
            ctf.status = CTFStatus.ARCHIVED
            logger.info("Archived CTF '%s' in guild %d", ctf.name, ctf.guild_id)
            await send_log(guild, None, "archive_ctf", f"Auto-archived **{ctf.name}** (CTF ended)")
        except discord.HTTPException as exc:
            logger.error("Failed to archive CTF '%s': %s", ctf.name, exc)

    # ── Weekly CTFTime Announcement ───────────────────────────────────────

    async def _weekly_ctftime_announcement(self) -> None:
        logger.info("Running weekly CTFTime announcement")
        try:
            events = await self._ctftime_client.fetch_week()
            embed = ctftime_events_embed(events, "Weekly CTF Digest \u2014 This Week's CTFs")
            embed.set_footer(text="Auto-posted every Monday 09:00 KST  \u2502  Data from ctftime.org")

            for guild in self._bot.guilds:
                channel = discord.utils.get(
                    guild.text_channels, name=self._announcement_channel
                )
                if channel:
                    try:
                        await channel.send(embed=embed)
                        logger.info("Sent weekly CTFTime digest to #%s in %s", channel.name, guild.name)
                    except discord.HTTPException as exc:
                        logger.warning("Failed to send digest to guild %s: %s", guild.id, exc)
        except Exception:
            logger.exception("Error in weekly CTFTime announcement")
