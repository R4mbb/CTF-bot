"""Tests for permission utility logic."""
from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

from bot.config import Config
from bot.utils.permissions import is_admin


def _make_member(*, manage_guild: bool = False, administrator: bool = False, roles: list[str] | None = None):
    member = MagicMock()
    perms = MagicMock()
    perms.manage_guild = manage_guild
    perms.administrator = administrator
    type(member).guild_permissions = PropertyMock(return_value=perms)

    mock_roles = []
    for name in (roles or []):
        r = MagicMock()
        r.name = name
        mock_roles.append(r)
    type(member).roles = PropertyMock(return_value=mock_roles)
    return member


def _make_interaction(member):
    interaction = MagicMock()
    interaction.user = member
    return interaction


def test_admin_by_manage_guild():
    config = Config.__new__(Config)
    object.__setattr__(config, "admin_role_name", "CTF Admin")
    member = _make_member(manage_guild=True)
    assert is_admin(_make_interaction(member), config) is True


def test_admin_by_role():
    config = Config.__new__(Config)
    object.__setattr__(config, "admin_role_name", "CTF Admin")
    member = _make_member(roles=["CTF Admin"])
    assert is_admin(_make_interaction(member), config) is True


def test_not_admin():
    config = Config.__new__(Config)
    object.__setattr__(config, "admin_role_name", "CTF Admin")
    member = _make_member(roles=["Member"])
    assert is_admin(_make_interaction(member), config) is False


def test_admin_by_administrator_perm():
    config = Config.__new__(Config)
    object.__setattr__(config, "admin_role_name", "CTF Admin")
    member = _make_member(administrator=True)
    assert is_admin(_make_interaction(member), config) is True
