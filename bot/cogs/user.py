"""User slash commands: join_ctf, leave_ctf, add_challenge, solve_challenge, list_*, ctf_info, help."""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import Config
from bot.db import get_session
from bot.services import ctf_service, audit
from bot.services.discord_service import (
    create_challenge_channel,
    get_channel_by_name,
    grant_user_access,
    mark_channel_solved,
    revoke_user_access,
)
from bot.services.discord_log import send_log
from bot.utils.embeds import (
    challenge_added_embed,
    challenge_list_embed,
    challenge_solved_embed,
    ctf_embed,
    ctf_list_embed,
    error_embed,
    success_embed,
)

logger = logging.getLogger(__name__)


async def _ctf_name_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    guild = interaction.guild
    if not guild:
        return []
    async with get_session() as session:
        ctfs = await ctf_service.list_ctfs(session, guild.id)
    return [
        app_commands.Choice(name=c.name, value=c.name)
        for c in ctfs
        if current.lower() in c.name.lower()
    ][:25]


async def _challenge_category_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    categories = [
        "web", "pwn", "rev", "crypto", "forensics", "misc",
        "osint", "stego", "blockchain", "hardware", "mobile", "ppc",
    ]
    return [
        app_commands.Choice(name=c, value=c)
        for c in categories
        if current.lower() in c
    ][:25]


# ── Help embed (static) ──────────────────────────────────────────────────

HELP_EMBED = discord.Embed(
    title="\U0001f4d6  CTF Bot \u2014 Command Guide",
    color=0x5865F2,
)
HELP_EMBED.add_field(
    name="\U0001f3ae  CTF Participation",
    value=(
        "`/join_ctf <ctf_name>` \u2014 Join a CTF, unlock channels\n"
        "`/leave_ctf <ctf_name>` \u2014 Leave a CTF\n"
        "`/list_ctfs` \u2014 List all CTFs in this server\n"
        "`/ctf_info <ctf_name>` \u2014 Detailed CTF info"
    ),
    inline=False,
)
HELP_EMBED.add_field(
    name="\U0001f3af  Challenge Tracking",
    value=(
        "`/add_challenge <ctf> <category> <name>` \u2014 Add a challenge\n"
        "`/solve_challenge <ctf> <category> <name>` \u2014 Mark as solved\n"
        "`/list_challenges <ctf_name>` \u2014 View challenge scoreboard"
    ),
    inline=False,
)
HELP_EMBED.add_field(
    name="\U0001f30d  CTFTime",
    value=(
        "`/upcoming_ctfs_week` \u2014 This week's CTFs from CTFTime\n"
        "`/upcoming_ctfs_month` \u2014 This month's CTFs"
    ),
    inline=False,
)
HELP_EMBED.add_field(
    name="\U0001f527  Admin Only",
    value=(
        "`/create_ctf` \u2014 Create a CTF (no args = form UI)\n"
        "`/create_ctf_from_ctftime <number>` \u2014 Quick-create from weekly list\n"
        "`/delete_ctf <ctf_name>` \u2014 Delete a CTF + channels\n"
        "`/delete_challenge <ctf> <cat> <name>` \u2014 Delete a challenge\n"
        "`/reload_ctfbot` \u2014 Reload bot extensions"
    ),
    inline=False,
)
HELP_EMBED.add_field(
    name="\U0001f4a1  Tips",
    value=(
        "\u2022 All CTF/category names support **autocomplete** \u2014 just start typing\n"
        "\u2022 Challenge categories (web, pwn, crypto...) also autocomplete\n"
        "\u2022 `/create_ctf_from_ctftime` uses the number from `/upcoming_ctfs_week`\n"
        "\u2022 After a CTF is created, a **Join** button appears in announcements"
    ),
    inline=False,
)
HELP_EMBED.set_footer(text="CTF Bot  \u2502  /help for this guide")


class UserCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config):
        self.bot = bot
        self.config = config

    # ── /help ─────────────────────────────────────────────────────────────

    @app_commands.command(name="help", description="Show command usage guide")
    async def help_cmd(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=HELP_EMBED, ephemeral=True)

    # ── /join_ctf ─────────────────────────────────────────────────────────

    @app_commands.command(name="join_ctf", description="Join a CTF to access its channels")
    @app_commands.describe(ctf_name="Name of the CTF to join")
    @app_commands.autocomplete(ctf_name=_ctf_name_autocomplete)
    async def join_ctf(self, interaction: discord.Interaction, ctf_name: str):
        guild = interaction.guild
        member = interaction.user
        assert guild and isinstance(member, discord.Member)

        await interaction.response.defer(ephemeral=True)

        async with get_session() as session:
            ctf = await ctf_service.get_ctf_by_name(session, guild.id, ctf_name)
            if not ctf:
                await interaction.followup.send(
                    embed=error_embed(f"CTF **{ctf_name}** not found."), ephemeral=True
                )
                return

            mem = await ctf_service.join_ctf(session, ctf.id, member.id, guild.id)
            if mem is None:
                await interaction.followup.send(
                    embed=error_embed("You have already joined this CTF."), ephemeral=True
                )
                return

            if ctf.category_id:
                category = guild.get_channel(ctf.category_id)
                if isinstance(category, discord.CategoryChannel):
                    await grant_user_access(category, member)

            await audit.log_action(
                session, guild.id, member.id, "join_ctf", f"Joined CTF '{ctf_name}'"
            )

        await send_log(guild, member, "join_ctf", f"Joined **{ctf_name}**")

        embed = discord.Embed(
            title="\U0001f3ae  Joined CTF",
            description=f"You are now a member of **{ctf_name}**.\nChannels are now visible in the category.",
            color=0x57F287,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /leave_ctf ────────────────────────────────────────────────────────

    @app_commands.command(name="leave_ctf", description="Leave a CTF")
    @app_commands.describe(ctf_name="Name of the CTF to leave")
    @app_commands.autocomplete(ctf_name=_ctf_name_autocomplete)
    async def leave_ctf(self, interaction: discord.Interaction, ctf_name: str):
        guild = interaction.guild
        member = interaction.user
        assert guild and isinstance(member, discord.Member)

        await interaction.response.defer(ephemeral=True)

        async with get_session() as session:
            ctf = await ctf_service.get_ctf_by_name(session, guild.id, ctf_name)
            if not ctf:
                await interaction.followup.send(
                    embed=error_embed(f"CTF **{ctf_name}** not found."), ephemeral=True
                )
                return

            removed = await ctf_service.leave_ctf(session, ctf.id, member.id)
            if not removed:
                await interaction.followup.send(
                    embed=error_embed("You are not a member of this CTF."), ephemeral=True
                )
                return

            if ctf.category_id:
                category = guild.get_channel(ctf.category_id)
                if isinstance(category, discord.CategoryChannel):
                    await revoke_user_access(category, member)

            await audit.log_action(
                session, guild.id, member.id, "leave_ctf", f"Left CTF '{ctf_name}'"
            )

        await send_log(guild, member, "leave_ctf", f"Left **{ctf_name}**")

        await interaction.followup.send(
            embed=success_embed(f"You left **{ctf_name}**."), ephemeral=True
        )

    # ── /add_challenge ────────────────────────────────────────────────────

    @app_commands.command(name="add_challenge", description="Add a challenge to a CTF")
    @app_commands.describe(
        ctf_name="CTF name",
        challenge_category="Category (e.g. web, pwn, crypto, rev, misc)",
        challenge_name="Challenge name",
        points="Points (optional)",
        challenge_url="Challenge URL (optional)",
        notes="Notes (optional)",
    )
    @app_commands.autocomplete(
        ctf_name=_ctf_name_autocomplete,
        challenge_category=_challenge_category_autocomplete,
    )
    async def add_challenge(
        self,
        interaction: discord.Interaction,
        ctf_name: str,
        challenge_category: str,
        challenge_name: str,
        points: int | None = None,
        challenge_url: str | None = None,
        notes: str | None = None,
    ):
        guild = interaction.guild
        assert guild

        await interaction.response.defer()

        async with get_session() as session:
            ctf = await ctf_service.get_ctf_by_name(session, guild.id, ctf_name)
            if not ctf:
                await interaction.followup.send(embed=error_embed(f"CTF **{ctf_name}** not found."))
                return

            chall = await ctf_service.add_challenge(
                session,
                ctf_id=ctf.id,
                category=challenge_category,
                name=challenge_name,
                added_by=interaction.user.id,
                points=points,
                challenge_url=challenge_url,
                notes=notes,
            )
            if chall is None:
                await interaction.followup.send(
                    embed=error_embed(
                        f"Challenge **[{challenge_category.upper()}] {challenge_name}** already exists."
                    ),
                )
                return

            await audit.log_action(
                session, guild.id, interaction.user.id, "add_challenge",
                f"Added [{challenge_category}] {challenge_name} to '{ctf_name}'",
            )

        embed = challenge_added_embed(
            challenge_name, challenge_category, ctf_name,
            points=points,
            added_by=interaction.user.display_name,
            notes=notes,
        )
        await interaction.followup.send(embed=embed)

        await send_log(
            guild, interaction.user, "add_challenge",
            f"Added **[{challenge_category.upper()}] {challenge_name}** to {ctf_name}",
        )

        # Create challenge channel + post to challenge-log
        if ctf.category_id:
            category = guild.get_channel(ctf.category_id)
            if isinstance(category, discord.CategoryChannel):
                await create_challenge_channel(category, challenge_category, challenge_name)

                log_ch = get_channel_by_name(category, "challenge-log")
                if log_ch:
                    try:
                        await log_ch.send(embed=embed)
                    except discord.HTTPException:
                        pass

    # ── /solve_challenge ──────────────────────────────────────────────────

    @app_commands.command(name="solve_challenge", description="Mark a challenge as solved")
    @app_commands.describe(
        ctf_name="CTF name",
        challenge_category="Challenge category",
        challenge_name="Challenge name",
        flag="Flag (optional, stored for reference)",
        writeup_url="Writeup URL (optional)",
        notes="Notes (optional)",
    )
    @app_commands.autocomplete(
        ctf_name=_ctf_name_autocomplete,
        challenge_category=_challenge_category_autocomplete,
    )
    async def solve_challenge(
        self,
        interaction: discord.Interaction,
        ctf_name: str,
        challenge_category: str,
        challenge_name: str,
        flag: str | None = None,
        writeup_url: str | None = None,
        notes: str | None = None,
    ):
        guild = interaction.guild
        assert guild

        await interaction.response.defer()

        async with get_session() as session:
            ctf = await ctf_service.get_ctf_by_name(session, guild.id, ctf_name)
            if not ctf:
                await interaction.followup.send(embed=error_embed(f"CTF **{ctf_name}** not found."))
                return

            chall = await ctf_service.get_challenge(
                session, ctf.id, challenge_category, challenge_name
            )
            if not chall:
                await interaction.followup.send(
                    embed=error_embed(
                        f"Challenge **[{challenge_category.upper()}] {challenge_name}** not found."
                    )
                )
                return

            if chall.solved:
                await interaction.followup.send(
                    embed=error_embed("This challenge is already solved.")
                )
                return

            solve = await ctf_service.solve_challenge(
                session,
                challenge_id=chall.id,
                user_id=interaction.user.id,
                flag=flag,
                writeup_url=writeup_url,
                notes=notes,
            )

            await audit.log_action(
                session, guild.id, interaction.user.id, "solve_challenge",
                f"Solved [{challenge_category}] {challenge_name} in '{ctf_name}'",
            )

        embed = challenge_solved_embed(
            challenge_name,
            challenge_category,
            ctf_name,
            solver=interaction.user.display_name,
            points=chall.points,
            writeup_url=writeup_url,
            notes=notes,
        )
        await interaction.followup.send(embed=embed)

        await send_log(
            guild, interaction.user, "solve_challenge",
            f"Solved **[{challenge_category.upper()}] {challenge_name}** in {ctf_name}",
        )

        # Rename challenge channel to ✅ prefix + post to challenge-log
        if ctf.category_id:
            category = guild.get_channel(ctf.category_id)
            if isinstance(category, discord.CategoryChannel):
                await mark_channel_solved(category, challenge_category, challenge_name)

                log_ch = get_channel_by_name(category, "challenge-log")
                if log_ch:
                    try:
                        await log_ch.send(embed=embed)
                    except discord.HTTPException:
                        pass

    # ── /list_ctfs ────────────────────────────────────────────────────────

    @app_commands.command(name="list_ctfs", description="List CTFs in this server")
    async def list_ctfs(self, interaction: discord.Interaction):
        guild = interaction.guild
        assert guild

        async with get_session() as session:
            ctfs = await ctf_service.list_ctfs(session, guild.id)

        embed = ctf_list_embed(ctfs)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /list_challenges ──────────────────────────────────────────────────

    @app_commands.command(name="list_challenges", description="List challenges for a CTF")
    @app_commands.describe(ctf_name="CTF name")
    @app_commands.autocomplete(ctf_name=_ctf_name_autocomplete)
    async def list_challenges(self, interaction: discord.Interaction, ctf_name: str):
        guild = interaction.guild
        assert guild

        async with get_session() as session:
            ctf = await ctf_service.get_ctf_by_name(session, guild.id, ctf_name)
            if not ctf:
                await interaction.response.send_message(
                    embed=error_embed(f"CTF **{ctf_name}** not found."), ephemeral=True
                )
                return

            challenges = await ctf_service.list_challenges(session, ctf.id)

        if not challenges:
            embed = discord.Embed(
                title=f"\U0001f3af  Challenges \u2014 {ctf_name}",
                description="*No challenges added yet.*\nUse `/add_challenge` to add one.",
                color=0x99AAB5,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        solved = sum(1 for c in challenges if c.solved)
        embed = challenge_list_embed(ctf_name, challenges, len(challenges), solved)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /ctf_info ─────────────────────────────────────────────────────────

    @app_commands.command(name="ctf_info", description="Show detailed info about a CTF")
    @app_commands.describe(ctf_name="CTF name")
    @app_commands.autocomplete(ctf_name=_ctf_name_autocomplete)
    async def ctf_info(self, interaction: discord.Interaction, ctf_name: str):
        guild = interaction.guild
        assert guild

        async with get_session() as session:
            ctf = await ctf_service.get_ctf_by_name(session, guild.id, ctf_name)
            if not ctf:
                await interaction.response.send_message(
                    embed=error_embed(f"CTF **{ctf_name}** not found."), ephemeral=True
                )
                return

            challenges = await ctf_service.list_challenges(session, ctf.id)
            member_count = await ctf_service.get_member_count(session, ctf.id)

        solved = sum(1 for c in challenges if c.solved)
        embed = ctf_embed(ctf, member_count=member_count, challenge_stats=(solved, len(challenges)))
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    config: Config = bot.config  # type: ignore[attr-defined]
    await bot.add_cog(UserCog(bot, config))
