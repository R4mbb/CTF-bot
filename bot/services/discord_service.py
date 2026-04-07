"""Discord category/channel management for CTFs."""
from __future__ import annotations

import logging
from typing import Sequence

import discord

logger = logging.getLogger(__name__)


def _find_general_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    """Find the GENERAL category (case-insensitive) to position new CTFs after it."""
    for cat in guild.categories:
        if cat.name.upper() == "GENERAL":
            return cat
    return None


async def create_ctf_category(
    guild: discord.Guild,
    ctf_name: str,
    admin_role: discord.Role | None,
    default_channels: list[str],
) -> tuple[discord.CategoryChannel, list[discord.TextChannel]]:
    """Create a hidden CTF category with default channels.

    The category is placed right after the GENERAL category if it exists.
    Returns the category and list of created channels.
    """
    # Category-level overwrites: hide from @everyone, show to admins
    overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
    }
    if admin_role:
        overwrites[admin_role] = discord.PermissionOverwrite(
            view_channel=True,
            manage_channels=True,
            manage_messages=True,
        )
    # Also always allow the bot itself
    if guild.me:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            manage_channels=True,
            manage_messages=True,
        )

    # Determine position: right after GENERAL category
    position: int | None = None
    general_cat = _find_general_category(guild)
    if general_cat is not None:
        position = general_cat.position + 1

    category = await guild.create_category(
        name=ctf_name,
        overwrites=overwrites,
        reason=f"CTF Bot: created CTF '{ctf_name}'",
    )

    # Move to desired position if we found GENERAL
    if position is not None:
        try:
            await category.edit(position=position)
        except discord.HTTPException:
            logger.warning("Could not reposition category '%s'", ctf_name)

    channels: list[discord.TextChannel] = []
    for ch_name in default_channels:
        ch = await category.create_text_channel(name=ch_name)
        channels.append(ch)

    logger.info("Created category '%s' with %d channels in guild %s", ctf_name, len(channels), guild.id)
    return category, channels


async def grant_user_access(
    category: discord.CategoryChannel,
    member: discord.Member,
) -> None:
    """Grant a user view access to a CTF category and all its channels."""
    overwrite = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    await category.set_permissions(member, overwrite=overwrite, reason="CTF Bot: user joined CTF")
    for channel in category.channels:
        await channel.set_permissions(member, overwrite=overwrite, reason="CTF Bot: user joined CTF")


async def revoke_user_access(
    category: discord.CategoryChannel,
    member: discord.Member,
) -> None:
    """Remove a user's permission overwrite from the CTF category."""
    await category.set_permissions(member, overwrite=None, reason="CTF Bot: user left CTF")
    for channel in category.channels:
        await channel.set_permissions(member, overwrite=None, reason="CTF Bot: user left CTF")


async def make_category_public(
    category: discord.CategoryChannel,
    guild: discord.Guild,
    team_role: discord.Role | None = None,
) -> None:
    """Make a CTF category visible after CTF ends.

    If team_role is provided, visibility is granted to that role only (read-only).
    Otherwise falls back to @everyone.
    """
    target = team_role or guild.default_role
    overwrite = discord.PermissionOverwrite(view_channel=True, send_messages=False)
    await category.set_permissions(
        target, overwrite=overwrite, reason="CTF Bot: CTF ended, archiving"
    )
    for channel in category.channels:
        await channel.set_permissions(
            target, overwrite=overwrite, reason="CTF Bot: CTF ended, archiving"
        )
    logger.info("Made category '%s' visible to %s in guild %s", category.name, target.name, guild.id)


async def delete_category_and_channels(category: discord.CategoryChannel) -> None:
    """Delete a category and all its channels."""
    for channel in category.channels:
        await channel.delete(reason="CTF Bot: CTF deleted")
    await category.delete(reason="CTF Bot: CTF deleted")
    logger.info("Deleted category '%s'", category.name)


def get_admin_role(guild: discord.Guild, role_name: str) -> discord.Role | None:
    return discord.utils.get(guild.roles, name=role_name)


def get_team_role(guild: discord.Guild, role_name: str) -> discord.Role | None:
    return discord.utils.get(guild.roles, name=role_name)


INIT_CHANNEL_PREFIX = "init-"

INIT_WELCOME_MESSAGE = (
    "## Welcome!\n\n"
    "This is your private registration channel.\n"
    "Type `/init` below to open the registration form.\n\n"
    "Your information is entered through a **private popup** — "
    "no one else can see what you type.\n\n"
    "After registration, this channel will be automatically deleted "
    "and you will gain access to all team channels."
)


async def create_init_channel(
    guild: discord.Guild,
    member: discord.Member,
    admin_role: discord.Role | None,
) -> discord.TextChannel:
    """Create a private #init-{username} channel visible only to the member and admins.

    Returns the created channel.
    """
    overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
        ),
    }
    if admin_role:
        overwrites[admin_role] = discord.PermissionOverwrite(
            view_channel=True,
            manage_channels=True,
            manage_messages=True,
        )
    if guild.me:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            manage_channels=True,
            manage_messages=True,
        )

    ch_name = f"{INIT_CHANNEL_PREFIX}{member.name}"
    channel = await guild.create_text_channel(
        name=ch_name,
        overwrites=overwrites,
        topic=f"Private registration channel for {member.display_name}",
        reason=f"CTF Bot: init channel for {member}",
    )
    await channel.send(f"{member.mention}\n\n{INIT_WELCOME_MESSAGE}")
    logger.info("Created private init channel #%s for %s in guild %s", ch_name, member, guild.id)
    return channel


async def delete_init_channel(
    guild: discord.Guild,
    member: discord.Member,
) -> bool:
    """Delete the private #init-{username} channel after registration.

    Returns True if a channel was deleted.
    """
    ch_name = f"{INIT_CHANNEL_PREFIX}{member.name}".lower().replace(" ", "-")
    for ch in guild.text_channels:
        if ch.name == ch_name:
            try:
                await ch.delete(reason=f"CTF Bot: {member} completed /init registration")
                logger.info("Deleted init channel #%s in guild %s", ch_name, guild.id)
                return True
            except discord.HTTPException as exc:
                logger.warning("Failed to delete init channel #%s: %s", ch_name, exc)
                return False
    return False


def get_channel_by_name(
    category: discord.CategoryChannel, name: str
) -> discord.TextChannel | None:
    for ch in category.channels:
        if isinstance(ch, discord.TextChannel) and ch.name == name:
            return ch
    return None


async def create_challenge_channel(
    category: discord.CategoryChannel,
    challenge_category: str,
    challenge_name: str,
) -> discord.TextChannel | None:
    """Create a text channel for a challenge at the bottom of the CTF category.

    Channel name format: {category}-{name} (e.g. web-sqli-login).
    Returns the channel or None on failure.
    """
    ch_name = f"{challenge_category}-{challenge_name}"
    try:
        ch = await category.create_text_channel(name=ch_name)
        logger.info("Created challenge channel '#%s' in '%s'", ch.name, category.name)
        return ch
    except discord.HTTPException as exc:
        logger.warning("Failed to create challenge channel '%s': %s", ch_name, exc)
        return None


async def delete_challenge_channel(
    category: discord.CategoryChannel,
    challenge_category: str,
    challenge_name: str,
) -> bool:
    """Delete the text channel for a challenge. Handles both unsolved and ✅-prefixed names.

    Returns True if a channel was deleted.
    """
    ch_name = f"{challenge_category}-{challenge_name}".lower().replace(" ", "-")
    solved_name = f"✅-{ch_name}"
    for ch in category.channels:
        if isinstance(ch, discord.TextChannel) and ch.name in (ch_name, solved_name):
            try:
                await ch.delete(reason="CTF Bot: challenge deleted")
                logger.info("Deleted challenge channel '#%s' in '%s'", ch.name, category.name)
                return True
            except discord.HTTPException as exc:
                logger.warning("Failed to delete channel '%s': %s", ch.name, exc)
                return False
    return False


async def mark_channel_solved(
    category: discord.CategoryChannel,
    challenge_category: str,
    challenge_name: str,
) -> bool:
    """Rename a challenge channel to prefix with ✅ to indicate it's solved.

    Returns True if renamed successfully.
    """
    ch_name = f"{challenge_category}-{challenge_name}"
    # Discord normalises channel names to lowercase with hyphens
    normalised = ch_name.lower().replace(" ", "-")
    for ch in category.channels:
        if isinstance(ch, discord.TextChannel) and ch.name == normalised:
            try:
                await ch.edit(name=f"✅-{normalised}", reason="CTF Bot: challenge solved")
                logger.info("Marked channel '#%s' as solved in '%s'", ch.name, category.name)
                return True
            except discord.HTTPException as exc:
                logger.warning("Failed to rename channel '%s': %s", ch.name, exc)
                return False
    return False
