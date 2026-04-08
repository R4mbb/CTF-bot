"""Admin-only slash commands: create_ctf, create_ctf_from_ctftime, delete_ctf, reload_ctfbot."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import Config
from bot.db import get_session
from bot.services import ctf_service, audit
from bot.services.discord_service import (
    create_ctf_category,
    delete_category_and_channels,
    delete_challenge_channel,
    get_admin_role,
    get_channel_by_name,
    grant_user_access,
)
from bot.services.discord_log import send_log
from bot.utils.embeds import ctf_created_embed, error_embed, success_embed
from bot.utils.permissions import is_admin

logger = logging.getLogger(__name__)


# ── Autocomplete ──────────────────────────────────────────────────────────

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


# ── Create CTF Modal ─────────────────────────────────────────────────────

class CreateCTFModal(discord.ui.Modal, title="Create New CTF"):
    ctf_name = discord.ui.TextInput(
        label="CTF Name",
        placeholder="e.g. DEF CON CTF 2026",
        max_length=200,
    )
    start_time = discord.ui.TextInput(
        label="Start Time (UTC)",
        placeholder="2026-06-15 09:00",
        max_length=20,
    )
    end_time = discord.ui.TextInput(
        label="End Time (UTC)",
        placeholder="2026-06-17 09:00",
        max_length=20,
    )
    ctftime_url = discord.ui.TextInput(
        label="CTFTime URL (optional)",
        placeholder="https://ctftime.org/event/...",
        required=False,
        max_length=500,
    )
    description = discord.ui.TextInput(
        label="Description (optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Brief description of the CTF...",
        required=False,
        max_length=1000,
    )

    def __init__(self, config: Config):
        super().__init__()
        self.config = config

    async def on_submit(self, interaction: discord.Interaction):
        try:
            start_dt = datetime.strptime(str(self.start_time), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            end_dt = datetime.strptime(str(self.end_time), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("Invalid time format. Use `YYYY-MM-DD HH:MM` (UTC)."),
                ephemeral=True,
            )
            return

        if end_dt <= start_dt:
            await interaction.response.send_message(
                embed=error_embed("End time must be after start time."), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        guild = interaction.guild
        assert guild is not None
        name = str(self.ctf_name).strip()
        desc = str(self.description).strip() or None
        url = str(self.ctftime_url).strip() or None

        ctf, channels_count = await _do_create_ctf(
            guild, self.config, name, start_dt, end_dt, desc, url, interaction.user,
        )
        if ctf is None:
            await interaction.followup.send(
                embed=error_embed(f"CTF **{name}** already exists."), ephemeral=True
            )
            return

        embed = ctf_created_embed(ctf, channels_count)
        await interaction.followup.send(embed=embed, ephemeral=True)


# ── Shared create logic ──────────────────────────────────────────────────

async def _do_create_ctf(
    guild: discord.Guild,
    config: Config,
    name: str,
    start_dt: datetime,
    end_dt: datetime,
    description: str | None,
    ctftime_url: str | None,
    actor: discord.User | discord.Member,
):
    """Shared logic for creating a CTF. Returns (CTF, channel_count) or (None, 0) on duplicate."""
    async with get_session() as session:
        existing = await ctf_service.get_ctf_by_name(session, guild.id, name)
        if existing:
            return None, 0

        admin_role = get_admin_role(guild, config.admin_role_name)
        category, channels = await create_ctf_category(
            guild, name, admin_role, config.default_channels
        )

        ctf = await ctf_service.create_ctf(
            session,
            guild_id=guild.id,
            name=name,
            start_time=start_dt,
            end_time=end_dt,
            description=description,
            ctftime_url=ctftime_url,
            visible_after_end=True,
            category_id=category.id,
        )

        await audit.log_action(
            session, guild.id, actor.id, "create_ctf",
            f"Created CTF '{name}' (id={ctf.id})",
        )

    # Post public join button to the guild-level #ctf-참여 channel
    ann_ch = discord.utils.get(guild.text_channels, name="ctf-참여")
    if ann_ch:
        join_embed = discord.Embed(
            title=f"\U0001f3c1  {name}",
            description=(
                f"**{discord.utils.format_dt(start_dt, 'f')}** \u2192 **{discord.utils.format_dt(end_dt, 'f')}**\n\n"
                + (f"{description}\n\n" if description else "")
                + (f"[CTFTime]({ctftime_url})\n\n" if ctftime_url else "")
                + "Click the button below to join and unlock all channels!"
            ),
            color=0x5865F2,
        )
        try:
            await ann_ch.send(embed=join_embed, view=JoinCTFView(name))
        except discord.HTTPException:
            pass

    # Log to #logs
    await send_log(guild, actor, "create_ctf", f"Created CTF **{name}**")

    return ctf, len(channels)


# ── Join CTF Button View ─────────────────────────────────────────────────

class JoinCTFView(discord.ui.View):
    def __init__(self, ctf_name: str):
        super().__init__(timeout=None)
        self.ctf_name = ctf_name

    @discord.ui.button(label="Join this CTF", style=discord.ButtonStyle.success, emoji="\U0001f3ae")
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member):
            return

        await interaction.response.defer(ephemeral=True)

        async with get_session() as session:
            ctf = await ctf_service.get_ctf_by_name(session, guild.id, self.ctf_name)
            if not ctf:
                await interaction.followup.send(
                    embed=error_embed("CTF not found."), ephemeral=True
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
                session, guild.id, member.id, "join_ctf",
                f"Joined CTF '{self.ctf_name}' (via button)",
            )

        await send_log(guild, member, "join_ctf", f"Joined **{self.ctf_name}**")

        await interaction.followup.send(
            embed=success_embed(f"You joined **{self.ctf_name}**! Channels are now visible."),
            ephemeral=True,
        )


# ── Confirm Delete View ──────────────────────────────────────────────────

class ConfirmDeleteView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        config: Config,
        author_id: int,
        ctf_name: str,
        guild: discord.Guild,
    ):
        super().__init__(timeout=30)
        self.bot = bot
        self.config = config
        self.author_id = author_id
        self.ctf_name = ctf_name
        self.guild = guild

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="\U0001f5d1")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                embed=error_embed("Not your action."), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        async with get_session() as session:
            ctf = await ctf_service.get_ctf_by_name(session, self.guild.id, self.ctf_name)
            if not ctf:
                await interaction.followup.send(
                    embed=error_embed(f"CTF **{self.ctf_name}** not found."), ephemeral=True
                )
                return

            # Always delete Discord category and channels
            if ctf.category_id:
                category = self.guild.get_channel(ctf.category_id)
                if isinstance(category, discord.CategoryChannel):
                    await delete_category_and_channels(category)

            await ctf_service.soft_delete_ctf(session, ctf)

            await audit.log_action(
                session, self.guild.id, interaction.user.id, "delete_ctf",
                f"Deleted CTF '{self.ctf_name}' (channels removed)",
            )

        await send_log(
            self.guild, interaction.user, "delete_ctf",
            f"Deleted **{self.ctf_name}** (channels removed)",
        )

        try:
            await interaction.followup.send(
                embed=success_embed(f"CTF **{self.ctf_name}** has been deleted."), ephemeral=True
            )
        except discord.HTTPException:
            # The channel this command was used in may have been deleted
            pass
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                embed=error_embed("Not your action."), ephemeral=True
            )
            return
        await interaction.response.edit_message(
            embed=success_embed("Deletion cancelled."), view=None
        )
        self.stop()


# ── Admin Cog ─────────────────────────────────────────────────────────────

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config):
        self.bot = bot
        self.config = config

    # ── /create_ctf ───────────────────────────────────────────────────────

    @app_commands.command(name="create_ctf", description="Create a new CTF (admin only). No args = form UI.")
    @app_commands.describe(
        ctf_name="CTF name (skip all params to use the form UI)",
        start_time="Start time UTC: YYYY-MM-DD HH:MM",
        end_time="End time UTC: YYYY-MM-DD HH:MM",
        description="Optional description",
        ctftime_url="Optional CTFTime URL",
    )
    async def create_ctf(
        self,
        interaction: discord.Interaction,
        ctf_name: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        description: str | None = None,
        ctftime_url: str | None = None,
    ):
        if not is_admin(interaction, self.config):
            await interaction.response.send_message(
                embed=error_embed("Admin permission required."), ephemeral=True
            )
            return

        if not ctf_name:
            await interaction.response.send_modal(CreateCTFModal(self.config))
            return

        if not start_time or not end_time:
            await interaction.response.send_message(
                embed=error_embed(
                    "Provide `start_time` and `end_time`, or use `/create_ctf` with no arguments to open the form."
                ),
                ephemeral=True,
            )
            return

        try:
            start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("Invalid time format. Use `YYYY-MM-DD HH:MM` (UTC)."),
                ephemeral=True,
            )
            return

        if end_dt <= start_dt:
            await interaction.response.send_message(
                embed=error_embed("End time must be after start time."), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        assert guild is not None

        ctf, ch_count = await _do_create_ctf(
            guild, self.config, ctf_name, start_dt, end_dt, description, ctftime_url, interaction.user,
        )
        if ctf is None:
            await interaction.followup.send(
                embed=error_embed(f"CTF **{ctf_name}** already exists."), ephemeral=True
            )
            return

        embed = ctf_created_embed(ctf, ch_count)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /create_ctf_from_ctftime ──────────────────────────────────────────

    @app_commands.command(
        name="create_ctf_from_ctftime",
        description="Create a CTF from upcoming_ctfs_week list number (admin only)",
    )
    @app_commands.describe(
        event_number="Event number from /upcoming_ctfs_week list",
        custom_name="Override CTF name (optional, default: CTFTime title)",
    )
    async def create_ctf_from_ctftime(
        self,
        interaction: discord.Interaction,
        event_number: int,
        custom_name: str | None = None,
    ):
        if not is_admin(interaction, self.config):
            await interaction.response.send_message(
                embed=error_embed("Admin permission required."), ephemeral=True
            )
            return

        # Get the CTFTime client from the CTFTimeCog
        ctftime_cog = self.bot.get_cog("CTFTimeCog")
        if not ctftime_cog or not hasattr(ctftime_cog, "client"):
            await interaction.response.send_message(
                embed=error_embed("CTFTime integration not loaded."), ephemeral=True
            )
            return

        client = ctftime_cog.client

        # If no events cached yet, fetch now
        if not client.last_week_events:
            await client.fetch_week()

        event = client.get_event_by_number(event_number)
        if not event:
            total = len(client.last_week_events)
            await interaction.response.send_message(
                embed=error_embed(
                    f"Event #{event_number} not found. "
                    + (f"Valid range: 1-{total}. " if total else "")
                    + "Run `/upcoming_ctfs_week` first."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        assert guild is not None

        name = custom_name or event.title
        ctf, ch_count = await _do_create_ctf(
            guild, self.config, name,
            event.start, event.finish,
            event.description[:500] if event.description else None,
            event.ctftime_url,
            interaction.user,
        )
        if ctf is None:
            await interaction.followup.send(
                embed=error_embed(f"CTF **{name}** already exists."), ephemeral=True
            )
            return

        embed = ctf_created_embed(ctf, ch_count)
        embed.add_field(
            name="\u200b",
            value=f"*Auto-filled from CTFTime event #{event_number}*",
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /delete_challenge ────────────────────────────────────────────────

    @app_commands.command(name="delete_challenge", description="Delete a challenge from a CTF (admin only)")
    @app_commands.describe(
        ctf_name="CTF name",
        challenge_category="Challenge category (e.g. web, pwn, crypto)",
        challenge_name="Challenge name",
    )
    @app_commands.autocomplete(ctf_name=_ctf_name_autocomplete)
    async def delete_challenge(
        self,
        interaction: discord.Interaction,
        ctf_name: str,
        challenge_category: str,
        challenge_name: str,
    ):
        if not is_admin(interaction, self.config):
            await interaction.response.send_message(
                embed=error_embed("Admin permission required."), ephemeral=True
            )
            return

        guild = interaction.guild
        assert guild is not None

        await interaction.response.defer(ephemeral=True)

        async with get_session() as session:
            ctf = await ctf_service.get_ctf_by_name(session, guild.id, ctf_name)
            if not ctf:
                await interaction.followup.send(
                    embed=error_embed(f"CTF **{ctf_name}** not found."), ephemeral=True
                )
                return

            chall = await ctf_service.delete_challenge(
                session, ctf.id, challenge_category, challenge_name
            )
            if not chall:
                await interaction.followup.send(
                    embed=error_embed(
                        f"Challenge **[{challenge_category.upper()}] {challenge_name}** not found."
                    ),
                    ephemeral=True,
                )
                return

            await audit.log_action(
                session, guild.id, interaction.user.id, "delete_challenge",
                f"Deleted [{challenge_category}] {challenge_name} from '{ctf_name}'",
            )

        # Delete the Discord channel for this challenge
        if ctf.category_id:
            category = guild.get_channel(ctf.category_id)
            if isinstance(category, discord.CategoryChannel):
                await delete_challenge_channel(category, challenge_category, challenge_name)

        await send_log(
            guild, interaction.user, "delete_challenge",
            f"Deleted **[{challenge_category.upper()}] {challenge_name}** from {ctf_name}",
        )

        await interaction.followup.send(
            embed=success_embed(
                f"Challenge **[{challenge_category.upper()}] {challenge_name}** deleted from **{ctf_name}**."
            ),
            ephemeral=True,
        )

    # ── /delete_ctf ───────────────────────────────────────────────────────

    @app_commands.command(name="delete_ctf", description="Delete a CTF and its channels (admin only)")
    @app_commands.describe(ctf_name="Name of the CTF to delete")
    @app_commands.autocomplete(ctf_name=_ctf_name_autocomplete)
    async def delete_ctf(
        self,
        interaction: discord.Interaction,
        ctf_name: str,
    ):
        if not is_admin(interaction, self.config):
            await interaction.response.send_message(
                embed=error_embed("Admin permission required."), ephemeral=True
            )
            return

        guild = interaction.guild
        assert guild is not None

        view = ConfirmDeleteView(
            self.bot, self.config, interaction.user.id, ctf_name, guild
        )
        embed = discord.Embed(
            title="\u26a0\ufe0f  Confirm Deletion",
            description=(
                f"**CTF:** {ctf_name}\n"
                f"**Category and all channels will be removed.**\n\n"
                f"*This action cannot be undone.*"
            ),
            color=0xED4245,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── /reload_ctfbot ────────────────────────────────────────────────────

    @app_commands.command(name="reload_ctfbot", description="Reload bot extensions and config (admin only)")
    async def reload_ctfbot(self, interaction: discord.Interaction):
        if not is_admin(interaction, self.config):
            await interaction.response.send_message(
                embed=error_embed("Admin permission required."), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        reloaded: list[str] = []
        errors: list[str] = []
        for ext_name in list(self.bot.extensions.keys()):
            try:
                await self.bot.reload_extension(ext_name)
                reloaded.append(ext_name)
            except Exception as exc:
                errors.append(f"`{ext_name}`: {exc}")
                logger.error("Failed to reload %s: %s", ext_name, exc)

        lines = [f"\u2705 Reloaded **{len(reloaded)}** extension(s)."]
        if errors:
            lines.append("\n**Errors:**")
            lines.extend(errors)

        async with get_session() as session:
            await audit.log_action(
                session, interaction.guild.id, interaction.user.id,
                "reload_ctfbot", f"Reloaded {len(reloaded)}, errors {len(errors)}",
            )

        await send_log(interaction.guild, interaction.user, "reload_ctfbot", "Reloaded bot extensions")

        await interaction.followup.send(
            embed=success_embed("\n".join(lines)), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    config: Config = bot.config  # type: ignore[attr-defined]
    await bot.add_cog(AdminCog(bot, config))
