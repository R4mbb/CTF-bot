"""Tests for CTF service logic."""
from __future__ import annotations

import pytest

from bot.models.ctf import CTFStatus
from bot.services.ctf_service import (
    add_challenge,
    create_ctf,
    get_achievements,
    get_challenge,
    get_ctf_by_category,
    get_ctf_by_name,
    get_leaderboard,
    get_member_count,
    join_ctf,
    leave_ctf,
    list_challenges,
    list_ctfs,
    set_announcement_message,
    set_challenge_channel,
    set_ctf_role,
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


@pytest.mark.asyncio
async def test_set_challenge_channel_persists_id(db_session):
    ctf = await create_ctf(
        db_session, guild_id=5, name="ChanCTF",
        start_time=hours_from_now(1), end_time=hours_from_now(25),
    )
    chall = await add_challenge(
        db_session, ctf_id=ctf.id, category="web", name="login", added_by=1,
    )
    assert chall.channel_id is None

    await set_challenge_channel(db_session, chall.id, 999_111)
    await db_session.flush()

    refreshed = await get_challenge(db_session, ctf.id, "web", "login")
    assert refreshed is not None
    assert refreshed.channel_id == 999_111


@pytest.mark.asyncio
async def test_get_ctf_by_category_resolves(db_session):
    ctf = await create_ctf(
        db_session, guild_id=7, name="CatCTF",
        start_time=hours_from_now(1), end_time=hours_from_now(25),
        category_id=424242,
    )
    found = await get_ctf_by_category(db_session, guild_id=7, category_id=424242)
    assert found is not None and found.id == ctf.id

    missing = await get_ctf_by_category(db_session, guild_id=7, category_id=999999)
    assert missing is None

    # Soft-deleted CTFs must not resolve.
    await soft_delete_ctf(db_session, ctf)
    await db_session.flush()
    assert await get_ctf_by_category(db_session, guild_id=7, category_id=424242) is None


def test_fmt_kst_appends_kst_label():
    from datetime import datetime, timezone
    from bot.utils.embeds import fmt_kst

    # 2026-05-06 00:00 UTC == 2026-05-06 09:00 KST
    formatted = fmt_kst(datetime(2026, 5, 6, 0, 0, tzinfo=timezone.utc))
    assert formatted == "2026-05-06 09:00 KST"


@pytest.mark.asyncio
async def test_set_ctf_role_persists(db_session):
    ctf = await create_ctf(
        db_session, guild_id=8, name="RoleCTF",
        start_time=hours_from_now(1), end_time=hours_from_now(25),
    )
    assert ctf.role_id is None
    await set_ctf_role(db_session, ctf.id, 555_222)
    await db_session.flush()
    refreshed = await get_ctf_by_name(db_session, 8, "RoleCTF")
    assert refreshed is not None and refreshed.role_id == 555_222


@pytest.mark.asyncio
async def test_leaderboard_orders_by_solve_count(db_session):
    """Sort key is solve count desc, then earliest first solve.

    Points intentionally don't enter the comparison — participants assign
    their own point values when adding challenges so a points-based ranking
    would be misleading.
    """
    ctf = await create_ctf(
        db_session, guild_id=9, name="LBCTF",
        start_time=hours_from_now(1), end_time=hours_from_now(25),
    )
    # User 1: one solve with a "big" point value (irrelevant to ordering).
    big = await add_challenge(
        db_session, ctf_id=ctf.id, category="web", name="big", added_by=1, points=10_000,
    )
    await solve_challenge(db_session, challenge_id=big.id, user_id=1)

    # User 2: two solves — should outrank user 1 by solve count alone.
    s1 = await add_challenge(
        db_session, ctf_id=ctf.id, category="pwn", name="s1", added_by=2, points=1,
    )
    s2 = await add_challenge(
        db_session, ctf_id=ctf.id, category="pwn", name="s2", added_by=2, points=1,
    )
    await solve_challenge(db_session, challenge_id=s1.id, user_id=2)
    await solve_challenge(db_session, challenge_id=s2.id, user_id=2)

    rows = await get_leaderboard(db_session, ctf.id)
    assert [r[:2] for r in rows] == [(2, 2), (1, 1)]


@pytest.mark.asyncio
async def test_leaderboard_ignores_null_points(db_session):
    """NULL-point challenges are still valid solves and must appear."""
    ctf = await create_ctf(
        db_session, guild_id=10, name="NullPtsCTF",
        start_time=hours_from_now(1), end_time=hours_from_now(25),
    )
    chall = await add_challenge(
        db_session, ctf_id=ctf.id, category="misc", name="x", added_by=1,  # points=None
    )
    await solve_challenge(db_session, challenge_id=chall.id, user_id=42)
    rows = await get_leaderboard(db_session, ctf.id)
    assert len(rows) == 1
    assert rows[0][:2] == (42, 1)


def test_auto_patch_adds_role_id_column():
    """Old DBs missing ctfs.role_id get the column added on init_db."""
    import asyncio
    import os
    import tempfile
    from sqlalchemy import create_engine, text

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = tmp.name
    try:
        eng = create_engine(f"sqlite:///{path}")
        with eng.begin() as c:
            # Pre-existing schema without role_id (mirrors the old layout).
            c.execute(text("""
                CREATE TABLE ctfs (
                    id INTEGER PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    description TEXT,
                    start_time DATETIME NOT NULL,
                    end_time DATETIME NOT NULL,
                    ctftime_url VARCHAR(500),
                    status VARCHAR(20) DEFAULT 'UPCOMING',
                    visible_after_end BOOLEAN DEFAULT 1,
                    category_id BIGINT,
                    deleted BOOLEAN DEFAULT 0,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """))

        async def run():
            from bot.db import init_db, close_db
            await init_db(f"sqlite+aiosqlite:///{path}")
            await close_db()

        asyncio.run(run())

        with eng.begin() as c:
            cols = {row[1] for row in c.exec_driver_sql("PRAGMA table_info(ctfs)")}
        assert "role_id" in cols
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_set_announcement_message_persists(db_session):
    ctf = await create_ctf(
        db_session, guild_id=11, name="AnnCTF",
        start_time=hours_from_now(1), end_time=hours_from_now(25),
    )
    assert ctf.announcement_message_id is None
    await set_announcement_message(db_session, ctf.id, 999_888_777)
    await db_session.flush()
    refreshed = await get_ctf_by_name(db_session, 11, "AnnCTF")
    assert refreshed is not None
    assert refreshed.announcement_message_id == 999_888_777


@pytest.mark.asyncio
async def test_get_achievements_first_blood_and_milestone(db_session):
    """First/second blood + first-to-N tracking via solve order."""
    import asyncio
    ctf = await create_ctf(
        db_session, guild_id=12, name="AchievementCTF",
        start_time=hours_from_now(1), end_time=hours_from_now(25),
    )
    # Five challenges; user 1 solves 4, user 2 solves 1.
    challs = []
    for i in range(5):
        c = await add_challenge(
            db_session, ctf_id=ctf.id, category="web", name=f"c{i}", added_by=1,
        )
        challs.append(c)

    # Order matters — solved_at uses datetime.now(); insert sequentially with
    # awaits so timestamps strictly increase.
    await solve_challenge(db_session, challenge_id=challs[0].id, user_id=1)  # first blood
    await asyncio.sleep(0.01)
    await solve_challenge(db_session, challenge_id=challs[1].id, user_id=2)  # second
    await asyncio.sleep(0.01)
    await solve_challenge(db_session, challenge_id=challs[2].id, user_id=1)
    await asyncio.sleep(0.01)
    await solve_challenge(db_session, challenge_id=challs[3].id, user_id=1)
    await asyncio.sleep(0.01)
    await solve_challenge(db_session, challenge_id=challs[4].id, user_id=1)  # user 1's 4th

    ach = await get_achievements(db_session, ctf.id, milestone=4)
    assert ach["first_blood"] is not None and ach["first_blood"][0] == 1
    assert ach["second_blood"] is not None and ach["second_blood"][0] == 2
    assert ach["first_to_milestone"] is not None
    assert ach["first_to_milestone"][0] == 1
    assert ach["milestone"] == 4


@pytest.mark.asyncio
async def test_get_achievements_handles_empty(db_session):
    ctf = await create_ctf(
        db_session, guild_id=13, name="EmptyAchievementCTF",
        start_time=hours_from_now(1), end_time=hours_from_now(25),
    )
    ach = await get_achievements(db_session, ctf.id)
    assert ach["first_blood"] is None
    assert ach["second_blood"] is None
    assert ach["first_to_milestone"] is None


@pytest.mark.asyncio
async def test_get_achievements_milestone_unreached(db_session):
    """Milestone returns None when no user has hit the threshold."""
    ctf = await create_ctf(
        db_session, guild_id=14, name="UnreachedCTF",
        start_time=hours_from_now(1), end_time=hours_from_now(25),
    )
    c1 = await add_challenge(db_session, ctf_id=ctf.id, category="web", name="x", added_by=1)
    await solve_challenge(db_session, challenge_id=c1.id, user_id=1)
    ach = await get_achievements(db_session, ctf.id, milestone=4)
    assert ach["first_blood"] is not None
    assert ach["first_to_milestone"] is None  # only 1 solve, milestone is 4


@pytest.mark.asyncio
async def test_solve_challenge_idempotent_per_user(db_session):
    """Same user double-submitting must not create two solve rows."""
    ctf = await create_ctf(
        db_session, guild_id=20, name="DupSolveCTF",
        start_time=hours_from_now(1), end_time=hours_from_now(25),
    )
    chall = await add_challenge(
        db_session, ctf_id=ctf.id, category="web", name="dup", added_by=1, points=100,
    )
    first = await solve_challenge(db_session, challenge_id=chall.id, user_id=42)
    assert first is not None
    second = await solve_challenge(db_session, challenge_id=chall.id, user_id=42)
    assert second is None  # idempotent — no second row

    rows = await get_leaderboard(db_session, ctf.id)
    assert rows[0][:2] == (42, 1)  # still 1 solve, not 2


@pytest.mark.asyncio
async def test_solve_challenge_allows_different_users(db_session):
    """Different users solving the same challenge each get their own row."""
    ctf = await create_ctf(
        db_session, guild_id=21, name="MultiSolveCTF",
        start_time=hours_from_now(1), end_time=hours_from_now(25),
    )
    chall = await add_challenge(
        db_session, ctf_id=ctf.id, category="web", name="shared", added_by=1, points=100,
    )
    a = await solve_challenge(db_session, challenge_id=chall.id, user_id=1)
    b = await solve_challenge(db_session, challenge_id=chall.id, user_id=2)
    assert a is not None and b is not None

    rows = await get_leaderboard(db_session, ctf.id)
    assert {r[0] for r in rows} == {1, 2}
    assert all(r[1] == 1 for r in rows)


@pytest.mark.asyncio
async def test_add_challenge_race_returns_none(db_session):
    """A duplicate INSERT (e.g. concurrent /add_challenge) returns None, not raises."""
    ctf = await create_ctf(
        db_session, guild_id=22, name="DupAddCTF",
        start_time=hours_from_now(1), end_time=hours_from_now(25),
    )
    first = await add_challenge(
        db_session, ctf_id=ctf.id, category="web", name="x", added_by=1,
    )
    assert first is not None
    # Sequential dup — caught by precheck.
    second = await add_challenge(
        db_session, ctf_id=ctf.id, category="web", name="x", added_by=2,
    )
    assert second is None
    # Session is still usable after the failed insert.
    third = await add_challenge(
        db_session, ctf_id=ctf.id, category="web", name="other", added_by=2,
    )
    assert third is not None


def test_normalise_challenge_name_truncates():
    from bot.services.discord_service import (
        DISCORD_CHANNEL_NAME_LIMIT,
        SOLVED_PREFIX,
        _normalise_challenge_name,
    )

    short = _normalise_challenge_name("web", "Login Page")
    assert short == "web-login-page"

    long_name = "x" * 200
    truncated = _normalise_challenge_name("web", long_name)
    # Solved prefix must always fit on top of the truncated base name.
    assert len(SOLVED_PREFIX) + len(truncated) <= DISCORD_CHANNEL_NAME_LIMIT
