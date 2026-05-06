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


CTF_ROLE_PREFIX = "ctf-"
# Discord role names are limited to 100 chars.
MAX_ROLE_NAME_LEN = 100


async def create_ctf_role(
    guild: discord.Guild, ctf_name: str
) -> discord.Role | None:
    """Create a per-CTF participant role.

    Returns the new Role, or ``None`` if creation failed (e.g. permissions or
    role-cap reached). Callers must tolerate ``None`` and fall back to the
    legacy per-member overwrite path so an unrecoverable role-creation failure
    never blocks CTF creation entirely.
    """
    base = f"{CTF_ROLE_PREFIX}{ctf_name}"
    name = base[:MAX_ROLE_NAME_LEN]
    try:
        role = await guild.create_role(
            name=name,
            colour=discord.Colour(0x5865F2),
            mentionable=True,
            reason=f"CTF Bot: participants role for '{ctf_name}'",
        )
        logger.info("Created CTF role '@%s' (id=%d) in guild %s", role.name, role.id, guild.id)
        return role
    except discord.HTTPException as exc:
        logger.warning("Failed to create CTF role for '%s': %s", ctf_name, exc)
        return None


async def delete_ctf_role(guild: discord.Guild, role_id: int) -> bool:
    """Delete a CTF participant role. Returns True on success."""
    role = guild.get_role(role_id)
    if role is None:
        return False
    try:
        await role.delete(reason="CTF Bot: CTF deleted")
        logger.info("Deleted CTF role '@%s' (id=%d)", role.name, role_id)
        return True
    except discord.HTTPException as exc:
        logger.warning("Failed to delete role id=%d: %s", role_id, exc)
        return False


async def assign_ctf_role(member: discord.Member, role: discord.Role) -> bool:
    try:
        await member.add_roles(role, reason="CTF Bot: joined CTF")
        return True
    except discord.HTTPException as exc:
        logger.warning("Failed to add role @%s to %s: %s", role.name, member, exc)
        return False


async def revoke_ctf_role(member: discord.Member, role: discord.Role) -> bool:
    try:
        await member.remove_roles(role, reason="CTF Bot: left CTF")
        return True
    except discord.HTTPException as exc:
        logger.warning("Failed to remove role @%s from %s: %s", role.name, member, exc)
        return False


async def create_ctf_category(
    guild: discord.Guild,
    ctf_name: str,
    admin_role: discord.Role | None,
    default_channels: list[str],
    ctf_role: discord.Role | None = None,
) -> tuple[discord.CategoryChannel, list[discord.TextChannel]]:
    """Create a hidden CTF category with default channels.

    If ``ctf_role`` is provided, it is added to the category overwrites with
    view+send permissions, so role assignment alone unlocks every channel
    inside the category (no per-member overwrites needed).

    The category is placed right after the GENERAL category if it exists.
    Returns the category and list of created channels.
    """
    # Category-level overwrites: hide from @everyone, show to admins
    overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
    }
    if ctf_role:
        overwrites[ctf_role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True
        )
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
    ctf_role: discord.Role | None = None,
) -> None:
    """Make a CTF category visible (read-only) after CTF ends.

    Adds a read-only overwrite for ``team_role`` (or @everyone) and, when the
    CTF used a per-CTF participant role, downgrades that role to read-only
    too — otherwise existing participants would still be able to chat in
    archived channels.
    """
    reason = "CTF Bot: CTF ended, archiving"
    read_only = discord.PermissionOverwrite(view_channel=True, send_messages=False)

    target = team_role or guild.default_role
    await category.set_permissions(target, overwrite=read_only, reason=reason)
    for channel in category.channels:
        await channel.set_permissions(target, overwrite=read_only, reason=reason)

    if ctf_role is not None:
        await category.set_permissions(ctf_role, overwrite=read_only, reason=reason)
        for channel in category.channels:
            await channel.set_permissions(ctf_role, overwrite=read_only, reason=reason)

    logger.info("Made category '%s' read-only via %s in guild %s", category.name, target.name, guild.id)


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


# Discord limits channel names to 100 characters. We reserve 4 for the "✅-"
# solved prefix (emoji + hyphen, leaving slack for future variants).
DISCORD_CHANNEL_NAME_LIMIT = 100
SOLVED_PREFIX = "✅-"
MAX_BASE_NAME_LEN = DISCORD_CHANNEL_NAME_LIMIT - len(SOLVED_PREFIX) - 2


def _normalise_challenge_name(challenge_category: str, challenge_name: str) -> str:
    """Build a Discord-friendly channel name and truncate so the solved prefix fits."""
    raw = f"{challenge_category}-{challenge_name}".lower().replace(" ", "-")
    if len(raw) > MAX_BASE_NAME_LEN:
        raw = raw[:MAX_BASE_NAME_LEN]
    return raw


def _find_existing_challenge_channel(
    category: discord.CategoryChannel, base_name: str
) -> discord.TextChannel | None:
    """Look up a challenge channel by either its base name or the solved variant."""
    solved_name = f"{SOLVED_PREFIX}{base_name}"
    for ch in category.channels:
        if isinstance(ch, discord.TextChannel) and ch.name in (base_name, solved_name):
            return ch
    return None


async def create_challenge_channel(
    category: discord.CategoryChannel,
    challenge_category: str,
    challenge_name: str,
) -> discord.TextChannel | None:
    """Create a text channel for a challenge.

    Channel name format: {category}-{name} (e.g. web-sqli-login), truncated to
    leave room for a future "✅-" solved prefix. Idempotent: if a channel
    already exists for this challenge (solved or not), it is returned instead
    of creating a duplicate.
    """
    base = _normalise_challenge_name(challenge_category, challenge_name)
    existing = _find_existing_challenge_channel(category, base)
    if existing is not None:
        logger.info("Challenge channel '#%s' already exists in '%s'", existing.name, category.name)
        return existing
    try:
        ch = await category.create_text_channel(name=base)
        logger.info("Created challenge channel '#%s' in '%s'", ch.name, category.name)
        return ch
    except discord.HTTPException as exc:
        logger.warning("Failed to create challenge channel '%s': %s", base, exc)
        return None


async def delete_challenge_channel(
    category: discord.CategoryChannel,
    challenge_category: str,
    challenge_name: str,
    *,
    channel_id: int | None = None,
) -> bool:
    """Delete the text channel for a challenge. Prefers a stored channel_id;
    falls back to name match (covering both unsolved and ✅-prefixed names).
    """
    target: discord.TextChannel | None = None
    if channel_id is not None:
        ch = category.guild.get_channel(channel_id)
        if isinstance(ch, discord.TextChannel) and ch.category_id == category.id:
            target = ch
    if target is None:
        base = _normalise_challenge_name(challenge_category, challenge_name)
        target = _find_existing_challenge_channel(category, base)
    if target is None:
        return False
    try:
        await target.delete(reason="CTF Bot: challenge deleted")
        logger.info("Deleted challenge channel '#%s' in '%s'", target.name, category.name)
        return True
    except discord.HTTPException as exc:
        logger.warning("Failed to delete channel '%s': %s", target.name, exc)
        return False


async def mark_channel_solved(
    category: discord.CategoryChannel,
    challenge_category: str,
    challenge_name: str,
    *,
    channel_id: int | None = None,
) -> bool:
    """Rename the challenge channel with a ✅- prefix.

    Locates the channel by stored channel_id when available (resilient to name
    normalisation differences) and falls back to a name lookup. The renamed
    name is truncated if necessary so it stays within Discord's 100-char limit.
    """
    target: discord.TextChannel | None = None
    if channel_id is not None:
        ch = category.guild.get_channel(channel_id)
        if isinstance(ch, discord.TextChannel) and ch.category_id == category.id:
            target = ch
    if target is None:
        base = _normalise_challenge_name(challenge_category, challenge_name)
        target = _find_existing_challenge_channel(category, base)
    if target is None:
        logger.warning(
            "mark_channel_solved: no channel found for [%s] %s in '%s'",
            challenge_category, challenge_name, category.name,
        )
        return False
    if target.name.startswith(SOLVED_PREFIX):
        return True

    new_name = f"{SOLVED_PREFIX}{target.name}"
    if len(new_name) > DISCORD_CHANNEL_NAME_LIMIT:
        # Defensive: shouldn't happen since create truncates, but guard anyway.
        new_name = new_name[:DISCORD_CHANNEL_NAME_LIMIT]
    try:
        await target.edit(name=new_name, reason="CTF Bot: challenge solved")
        logger.info("Marked channel '#%s' as solved in '%s'", target.name, category.name)
        return True
    except discord.HTTPException as exc:
        logger.warning("Failed to rename channel '%s': %s", target.name, exc)
        return False


async def reorder_ctf_channels(
    category: discord.CategoryChannel,
    default_channels: Sequence[str],
) -> None:
    """Reorder channels inside a CTF category.

    Order:
      1. Default/system channels (announcements, general, ...) in config order.
      2. Unsolved challenge channels, sorted by name (groups them by category prefix).
      3. Solved (``✅-``) challenge channels, sorted by name.

    Per-channel skip: channels already at their target index are left alone,
    so the typical add/solve costs 1–2 ``edit(position=...)`` calls instead of
    one per channel — important under a burst of concurrent adds where
    Discord's per-channel rate limit would otherwise stretch responses out.
    """
    text_channels = [
        ch for ch in category.channels if isinstance(ch, discord.TextChannel)
    ]
    by_name = {ch.name: ch for ch in text_channels}
    default_set = set(default_channels)

    ordered: list[discord.TextChannel] = []
    for name in default_channels:
        ch = by_name.get(name)
        if ch is not None:
            ordered.append(ch)

    others = [ch for ch in text_channels if ch.name not in default_set]
    unsolved = sorted(
        (ch for ch in others if not ch.name.startswith(SOLVED_PREFIX)),
        key=lambda c: c.name,
    )
    solved = sorted(
        (ch for ch in others if ch.name.startswith(SOLVED_PREFIX)),
        key=lambda c: c.name,
    )
    ordered.extend(unsolved)
    ordered.extend(solved)

    current = sorted(text_channels, key=lambda c: c.position)
    if current == ordered:
        return

    # Snapshot positions ONCE — Discord auto-shifts siblings when one channel
    # moves, but the shifts are predictable and we make decisions from this
    # snapshot. Worst case is one harmless extra edit; never a missed move.
    initial_positions = {ch.id: ch.position for ch in text_channels}
    for index, ch in enumerate(ordered):
        if initial_positions.get(ch.id) == index:
            continue
        try:
            await ch.edit(position=index, reason="CTF Bot: reorder challenge channels")
        except discord.HTTPException as exc:
            logger.debug("Reposition failed for #%s: %s", ch.name, exc)
