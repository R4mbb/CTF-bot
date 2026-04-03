"""CTFTime integration commands + weekly auto-announcement."""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.integrations.ctftime import CTFTimeClient
from bot.utils.embeds import ctftime_events_embed

logger = logging.getLogger(__name__)

SCHEDULE_CHANNEL = "ctf-일정"


class CTFTimeCog(commands.Cog):
    def __init__(self, bot: commands.Bot, client: CTFTimeClient):
        self.bot = bot
        self.client = client

    async def _send_to_schedule_channel(
        self, interaction: discord.Interaction, embed: discord.Embed
    ) -> None:
        """Send embed to #ctf-일정. If the command was used elsewhere, post there and notify the user."""
        guild = interaction.guild
        if not guild:
            await interaction.followup.send(embed=embed)
            return

        target = discord.utils.get(guild.text_channels, name=SCHEDULE_CHANNEL)

        if target and target.id != interaction.channel_id:
            # Post to #ctf-일정 and tell the user where it went
            await target.send(embed=embed)
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"\u2705  {target.mention} 에 게시했습니다.",
                    color=0x57F287,
                ),
                ephemeral=True,
            )
        elif target:
            # Already in #ctf-일정, just post here
            await interaction.followup.send(embed=embed)
        else:
            # Channel doesn't exist, just reply in place
            await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="upcoming_ctfs_week",
        description="Show upcoming CTFs this week from CTFTime",
    )
    async def upcoming_week(self, interaction: discord.Interaction):
        await interaction.response.defer()
        events = await self.client.fetch_week()
        embed = ctftime_events_embed(events, "Upcoming CTFs \u2014 This Week")
        await self._send_to_schedule_channel(interaction, embed)

    @app_commands.command(
        name="upcoming_ctfs_month",
        description="Show upcoming CTFs this month from CTFTime",
    )
    async def upcoming_month(self, interaction: discord.Interaction):
        await interaction.response.defer()
        events = await self.client.fetch_month()
        embed = ctftime_events_embed(events, "Upcoming CTFs \u2014 This Month")
        await self._send_to_schedule_channel(interaction, embed)


async def setup(bot: commands.Bot) -> None:
    from bot.config import Config
    config: Config = bot.config  # type: ignore[attr-defined]
    client = CTFTimeClient(cache_ttl=config.ctftime_cache_ttl)
    await bot.add_cog(CTFTimeCog(bot, client))
