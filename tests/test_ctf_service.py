"""Tests for CTF service logic."""
from __future__ import annotations

import pytest

from bot.models.ctf import CTFStatus
from bot.services.ctf_service import (
    add_challenge,
    create_ctf,
    get_challenge,
    get_ctf_by_name,
    get_member_count,
    join_ctf,
    leave_ctf,
    list_challenges,
    list_ctfs,
    soft_delete_ctf,
    solve_challenge,
)
from tests.conftest import hours_from_now


@pytest.mark.asyncio
async def test_create_and_get_ctf(db_session):
    ctf = await create_ctf(
        db_session,
        guild_id=1,
        name="TestCTF",
        start_time=hours_from_now(1),
        end_time=hours_from_now(25),
    )
    assert ctf.id is not None
    assert ctf.name == "TestCTF"

    found = await get_ctf_by_name(db_session, 1, "TestCTF")
    assert found is not None
    assert found.id == ctf.id


@pytest.mark.asyncio
async def test_ctf_status_computation(db_session):
    # Upcoming
    ctf = await create_ctf(
        db_session,
        guild_id=1,
        name="FutureCTF",
        start_time=hours_from_now(10),
        end_time=hours_from_now(34),
    )
    assert ctf.compute_status() == CTFStatus.UPCOMING

    # Active
    ctf2 = await create_ctf(
        db_session,
        guild_id=1,
        name="ActiveCTF",
        start_time=hours_from_now(-1),
        end_time=hours_from_now(23),
    )
    assert ctf2.compute_status() == CTFStatus.ACTIVE

    # Ended
    ctf3 = await create_ctf(
        db_session,
        guild_id=1,
        name="PastCTF",
        start_time=hours_from_now(-48),
        end_time=hours_from_now(-24),
    )
    assert ctf3.compute_status() == CTFStatus.ENDED


@pytest.mark.asyncio
async def test_soft_delete(db_session):
    ctf = await create_ctf(
        db_session, guild_id=2, name="DelCTF",
        start_time=hours_from_now(1), end_time=hours_from_now(25),
    )
    await soft_delete_ctf(db_session, ctf)
    await db_session.flush()

    found = await get_ctf_by_name(db_session, 2, "DelCTF")
    assert found is None


@pytest.mark.asyncio
async def test_join_and_leave(db_session):
    ctf = await create_ctf(
        db_session, guild_id=3, name="JoinCTF",
        start_time=hours_from_now(1), end_time=hours_from_now(25),
    )
    mem = await join_ctf(db_session, ctf.id, user_id=100, guild_id=3)
    assert mem is not None

    # Duplicate join returns None
    dup = await join_ctf(db_session, ctf.id, user_id=100, guild_id=3)
    assert dup is None

    # Member count
    count = await get_member_count(db_session, ctf.id)
    assert count == 1

    # Leave
    assert await leave_ctf(db_session, ctf.id, user_id=100) is True
    assert await leave_ctf(db_session, ctf.id, user_id=100) is False


@pytest.mark.asyncio
async def test_challenge_lifecycle(db_session):
    ctf = await create_ctf(
        db_session, guild_id=4, name="ChallCTF",
        start_time=hours_from_now(1), end_time=hours_from_now(25),
    )

    # Add challenge
    chall = await add_challenge(
        db_session, ctf_id=ctf.id, category="web", name="SQLi101",
        added_by=200, points=100,
    )
    assert chall is not None
    assert chall.solved is False

    # Duplicate check
    dup = await add_challenge(
        db_session, ctf_id=ctf.id, category="web", name="SQLi101", added_by=201,
    )
    assert dup is None

    # Solve
    solve = await solve_challenge(
        db_session, challenge_id=chall.id, user_id=200, flag="flag{test}",
    )
    assert solve is not None

    # Verify solved status
    chall_after = await get_challenge(db_session, ctf.id, "web", "SQLi101")
    assert chall_after is not None
    assert chall_after.solved is True

    # List
    challs = await list_challenges(db_session, ctf.id)
    assert len(challs) == 1
