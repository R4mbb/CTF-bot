"""Send bot activity logs to a Discord #logs channel."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord

logger = logging.getLogger(__name__)

LOG_CHANNEL_NAME = "logs"

# Compact action icons
ACTION_ICONS = {
    "create_ctf": "\U0001f4e6",     # package
    "delete_ctf": "\U0001f5d1",     # wastebasket
    "join_ctf": "\U0001f44b",       # wave
    "leave_ctf": "\U0001f6aa",      # door
    "add_challenge": "\U0001f4cc",  # pushpin
    "solve_challenge": "\U0001f389",# party
    "reload_ctfbot": "\U0001f504",  # arrows
    "create_ctf_from_ctftime": "\U0001f310",  # globe
    "archive_ctf": "\U0001f4e6",    # package
}


async def send_log(
    guild: discord.Guild,
    user: discord.User | discord.Member | None,
    action: str,
    detail: str,
) -> None:
    """Post a one-line log embed to #logs if the channel exists."""
    channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)
    if not channel:
        return

    icon = ACTION_ICONS.get(action, "\U0001f4cb")
    user_str = f"**{user.display_name}**" if user else "System"
    now = discord.utils.format_dt(datetime.now(timezone.utc), "T")

    embed = discord.Embed(
        description=f"{icon} {now}  {user_str} \u2014 {detail}",
        color=0x2B2D31,
    )

    try:
        await channel.send(embed=embed)
    except discord.HTTPException as exc:
        logger.debug("Could not send to #logs in %s: %s", guild.id, exc)
