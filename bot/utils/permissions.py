from __future__ import annotations

import discord
from discord import Interaction

from bot.config import Config


def is_admin(interaction: Interaction, config: Config) -> bool:
    """Check if the interaction user is a bot admin.

    Admin = has Manage Guild permission OR has the configured admin role.
    """
    member = interaction.user
    if not hasattr(member, "guild_permissions"):
        return False

    if member.guild_permissions.manage_guild or member.guild_permissions.administrator:
        return True

    return any(role.name == config.admin_role_name for role in member.roles)


def admin_check(config: Config):
    """Decorator-compatible check for app_commands."""
    from discord import app_commands

    async def predicate(interaction: Interaction) -> bool:
        if not is_admin(interaction, config):
            await interaction.response.send_message(
                "You do not have permission to use this command.", ephemeral=True
            )
            return False
        return True

    return app_commands.check(predicate)
