"""CTF Bot entry point."""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import Config
from bot.db import close_db, init_db
from bot.scheduler import CTFScheduler
from bot.utils.embeds import error_embed

EXTENSIONS = [
    "bot.cogs.admin",
    "bot.cogs.user",
    "bot.cogs.ctftime_cog",
]


def setup_logging(level: str) -> None:
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=fmt)
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


logger = logging.getLogger("ctfbot")


class CTFBot(commands.Bot):
    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.members = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            application_id=int(config.discord_app_id),
        )
        self.config = config
        self._scheduler: CTFScheduler | None = None

    async def setup_hook(self) -> None:
        await init_db(self.config.database_url)

        for ext in EXTENSIONS:
            await self.load_extension(ext)
            logger.info("Loaded extension: %s", ext)

        # Sync slash commands
        if self.config.dev_guild_id:
            guild = discord.Object(id=self.config.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Synced commands to dev guild %s", self.config.dev_guild_id)
        else:
            await self.tree.sync()
            logger.info("Synced commands globally")

        # Global error handler for slash commands
        self.tree.on_error = self._on_app_command_error

        # Start scheduler
        self._scheduler = CTFScheduler(
            self,
            interval_minutes=self.config.scheduler_interval_minutes,
            announcement_channel=self.config.announcement_channel or None,
            ctftime_cache_ttl=self.config.ctftime_cache_ttl,
            team_role_name=self.config.team_role_name,
        )
        self._scheduler.start()

    async def close(self) -> None:
        if self._scheduler:
            self._scheduler.stop()
        await close_db()
        await super().close()

    async def on_ready(self) -> None:
        logger.info("Bot ready as %s (ID: %s)", self.user, self.user.id if self.user else "?")
        logger.info("Guilds: %d", len(self.guilds))

    async def _on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        logger.error("Command error in /%s: %s", interaction.command.name if interaction.command else "?", error)

        msg = "An unexpected error occurred. Please try again."
        if isinstance(error, app_commands.CheckFailure):
            msg = "You do not have permission to use this command."
        elif isinstance(error, app_commands.CommandInvokeError) and error.original:
            logger.exception("Original exception:", exc_info=error.original)

        embed = error_embed(msg)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass


def main() -> None:
    config = Config()
    setup_logging(config.log_level)
    bot = CTFBot(config)
    bot.run(config.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
