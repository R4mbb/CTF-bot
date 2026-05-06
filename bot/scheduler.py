"""Background scheduler for CTF lifecycle management."""
from __future__ import annotations

import logging

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.db import get_session
from bot.services.archive import archive_ctf
from bot.services.ctf_service import get_ended_ctfs_needing_archive
from bot.services.discord_log import send_log

logger = logging.getLogger(__name__)


class CTFScheduler:
    def __init__(
        self,
        bot: discord.Client,
        interval_minutes: int = 5,
        team_role_name: str = "팀원",
    ):
        self._bot = bot
        self._scheduler = AsyncIOScheduler()
        self._interval = interval_minutes
        self._team_role_name = team_role_name

    def start(self) -> None:
        self._scheduler.add_job(
            self._check_ctf_lifecycle,
            "interval",
            minutes=self._interval,
            id="ctf_lifecycle",
            replace_existing=True,
        )

        self._scheduler.start()
        logger.info("Scheduler started (lifecycle interval=%d min)", self._interval)

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    async def _check_ctf_lifecycle(self) -> None:
        logger.debug("Running CTF lifecycle check")
        try:
            async with get_session() as session:
                ctfs = await get_ended_ctfs_needing_archive(session)
                for ctf in ctfs:
                    guild = self._bot.get_guild(ctf.guild_id)
                    if guild is None:
                        logger.warning("Guild %d not found for CTF '%s'", ctf.guild_id, ctf.name)
                        continue
                    try:
                        await archive_ctf(
                            ctf, guild, session,
                            team_role_name=self._team_role_name,
                            reason="auto-archive",
                        )
                        await send_log(
                            guild, None, "archive_ctf",
                            f"Auto-archived **{ctf.name}** (CTF ended)",
                        )
                    except Exception:
                        logger.exception("Error archiving CTF '%s'", ctf.name)
        except Exception:
            logger.exception("Error in CTF lifecycle check")
