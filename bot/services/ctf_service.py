"""Business logic for CTF operations (DB layer)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.ctf import CTF, CTFStatus
from bot.models.membership import CTFMembership
from bot.models.challenge import Challenge
from bot.models.solve import ChallengeSolve


# ── CTF CRUD ──────────────────────────────────────────────────────────────

async def create_ctf(
    session: AsyncSession,
    *,
    guild_id: int,
    name: str,
    start_time: datetime,
    end_time: datetime,
    description: str | None = None,
    ctftime_url: str | None = None,
    visible_after_end: bool = True,
    category_id: int | None = None,
) -> CTF:
    ctf = CTF(
        guild_id=guild_id,
        name=name,
        start_time=start_time,
        end_time=end_time,
        description=description,
        ctftime_url=ctftime_url,
        visible_after_end=visible_after_end,
        category_id=category_id,
    )
    session.add(ctf)
    await session.flush()
    return ctf


async def get_ctf_by_name(session: AsyncSession, guild_id: int, name: str) -> CTF | None:
    stmt = select(CTF).where(CTF.guild_id == guild_id, CTF.name == name, CTF.deleted == False)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_ctf_by_id(session: AsyncSession, ctf_id: int) -> CTF | None:
    stmt = select(CTF).where(CTF.id == ctf_id, CTF.deleted == False)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_ctf_by_category(
    session: AsyncSession, guild_id: int, category_id: int
) -> CTF | None:
    """Find the (non-deleted) CTF whose Discord category matches the given id."""
    stmt = select(CTF).where(
        CTF.guild_id == guild_id,
        CTF.category_id == category_id,
        CTF.deleted == False,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_ctfs(session: AsyncSession, guild_id: int, include_deleted: bool = False) -> list[CTF]:
    stmt = select(CTF).where(CTF.guild_id == guild_id)
    if not include_deleted:
        stmt = stmt.where(CTF.deleted == False)
    stmt = stmt.order_by(CTF.start_time.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def soft_delete_ctf(session: AsyncSession, ctf: CTF) -> None:
    ctf.deleted = True


async def set_ctf_role(session: AsyncSession, ctf_id: int, role_id: int | None) -> None:
    """Persist the Discord role id used for CTF participants."""
    result = await session.execute(select(CTF).where(CTF.id == ctf_id))
    ctf = result.scalar_one_or_none()
    if ctf is not None:
        ctf.role_id = role_id


async def set_announcement_message(
    session: AsyncSession, ctf_id: int, message_id: int | None
) -> None:
    """Persist the Discord message id of the CTF's announcement embed.

    Stored so we can edit that exact message later (e.g. to refresh the live
    participant counter on join/leave).
    """
    result = await session.execute(select(CTF).where(CTF.id == ctf_id))
    ctf = result.scalar_one_or_none()
    if ctf is not None:
        ctf.announcement_message_id = message_id


async def get_ended_ctfs_needing_archive(session: AsyncSession) -> list[CTF]:
    """Find CTFs that have ended, are visible_after_end, and not yet archived."""
    now = datetime.now(timezone.utc)
    stmt = select(CTF).where(
        CTF.end_time < now,
        CTF.visible_after_end == True,
        CTF.status != CTFStatus.ARCHIVED,
        CTF.deleted == False,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ── Membership ────────────────────────────────────────────────────────────

async def join_ctf(session: AsyncSession, ctf_id: int, user_id: int, guild_id: int) -> CTFMembership | None:
    """Return membership or None if already joined."""
    existing = await session.execute(
        select(CTFMembership).where(
            CTFMembership.ctf_id == ctf_id,
            CTFMembership.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        return None
    mem = CTFMembership(ctf_id=ctf_id, user_id=user_id, guild_id=guild_id)
    session.add(mem)
    await session.flush()
    return mem


async def leave_ctf(session: AsyncSession, ctf_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(CTFMembership).where(
            CTFMembership.ctf_id == ctf_id,
            CTFMembership.user_id == user_id,
        )
    )
    mem = result.scalar_one_or_none()
    if not mem:
        return False
    await session.delete(mem)
    return True


async def get_member_count(session: AsyncSession, ctf_id: int) -> int:
    result = await session.execute(
        select(func.count()).select_from(CTFMembership).where(CTFMembership.ctf_id == ctf_id)
    )
    return result.scalar_one()


async def is_member(session: AsyncSession, ctf_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(CTFMembership).where(
            CTFMembership.ctf_id == ctf_id,
            CTFMembership.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


# ── Challenges ────────────────────────────────────────────────────────────

async def add_challenge(
    session: AsyncSession,
    *,
    ctf_id: int,
    category: str,
    name: str,
    added_by: int,
    points: int | None = None,
    challenge_url: str | None = None,
    notes: str | None = None,
) -> Challenge | None:
    """Return Challenge or None if a row with the same ``(ctf_id, category, name)`` exists.

    Same race-tolerance pattern as ``solve_challenge``: cheap precheck for the
    common case, and a savepoint around the actual INSERT so a concurrent
    duplicate from a sibling session is surfaced as a clean ``None`` rather
    than a generic 'unexpected error' from the global error handler.
    """
    existing = await session.execute(
        select(Challenge).where(
            Challenge.ctf_id == ctf_id,
            Challenge.category == category,
            Challenge.name == name,
        )
    )
    if existing.scalar_one_or_none():
        return None
    chall = Challenge(
        ctf_id=ctf_id,
        category=category,
        name=name,
        added_by=added_by,
        points=points,
        challenge_url=challenge_url,
        notes=notes,
    )
    try:
        async with session.begin_nested():
            session.add(chall)
    except IntegrityError:
        return None
    return chall


async def set_challenge_channel(
    session: AsyncSession, challenge_id: int, channel_id: int | None
) -> None:
    """Persist the Discord channel id for a challenge."""
    result = await session.execute(
        select(Challenge).where(Challenge.id == challenge_id)
    )
    chall = result.scalar_one_or_none()
    if chall is not None:
        chall.channel_id = channel_id


async def solve_challenge(
    session: AsyncSession,
    *,
    challenge_id: int,
    user_id: int,
    flag: str | None = None,
    writeup_url: str | None = None,
    notes: str | None = None,
) -> ChallengeSolve | None:
    """Record a solve; returns ``None`` if this user already solved this challenge.

    Two layers of protection against double-counting:

    1. **Precheck** — most retries (double-click, network retry, sequential
       resubmit) hit this and short-circuit cheaply.
    2. **Savepoint + UNIQUE constraint** — for true concurrency where two
       sessions both pass the precheck, the DB rejects the second INSERT and
       the savepoint roll-back keeps the outer transaction usable.
    """
    # 1. Cheap precheck for the sequential / retry case.
    existing = await session.execute(
        select(ChallengeSolve).where(
            ChallengeSolve.challenge_id == challenge_id,
            ChallengeSolve.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return None

    # 2. chall.solved is idempotent — even the loser of a race may set it.
    chall = (await session.execute(
        select(Challenge).where(Challenge.id == challenge_id)
    )).scalar_one()
    chall.solved = True

    # 3. Savepoint so a UNIQUE-violation doesn't poison the outer transaction.
    solve = ChallengeSolve(
        challenge_id=challenge_id,
        user_id=user_id,
        flag=flag,
        writeup_url=writeup_url,
        notes=notes,
    )
    try:
        async with session.begin_nested():
            session.add(solve)
    except IntegrityError:
        return None
    return solve


async def get_challenge(
    session: AsyncSession, ctf_id: int, category: str, name: str
) -> Challenge | None:
    result = await session.execute(
        select(Challenge).where(
            Challenge.ctf_id == ctf_id,
            Challenge.category == category,
            Challenge.name == name,
        )
    )
    return result.scalar_one_or_none()


async def list_challenges(session: AsyncSession, ctf_id: int) -> list[Challenge]:
    result = await session.execute(
        select(Challenge).where(Challenge.ctf_id == ctf_id).order_by(Challenge.category, Challenge.name)
    )
    return list(result.scalars().all())


async def get_leaderboard(
    session: AsyncSession, ctf_id: int
) -> list[tuple[int, int, datetime]]:
    """Per-user solve aggregates for a CTF.

    Returns ``(user_id, solve_count, first_solve_at)`` rows, ordered by solve
    count descending, then earliest first solve. Points are intentionally
    omitted — participants assign their own point values when adding
    challenges, so a "total points" comparison can be misleading rather than
    informative.
    """
    solves_lbl = func.count(ChallengeSolve.id).label("solves")
    first_lbl = func.min(ChallengeSolve.solved_at).label("first_solve")
    stmt = (
        select(ChallengeSolve.user_id, solves_lbl, first_lbl)
        .where(ChallengeSolve.challenge_id.in_(
            select(Challenge.id).where(Challenge.ctf_id == ctf_id)
        ))
        .group_by(ChallengeSolve.user_id)
        .order_by(desc(solves_lbl), first_lbl)
    )
    result = await session.execute(stmt)
    return [(row.user_id, row.solves, row.first_solve) for row in result]


async def get_achievements(
    session: AsyncSession, ctf_id: int, *, milestone: int = 4
) -> dict:
    """Compute notable achievements for a CTF using Discord-tracked timestamps.

    Returns a dict with keys:
      - ``first_blood``      → ``(user_id, solved_at)`` of the first solve
      - ``second_blood``     → ``(user_id, solved_at)`` of the second solve
      - ``first_to_milestone`` → first user to reach ``milestone`` total solves
      - ``milestone``        → echoes the input ``milestone`` (default 4)

    Each value is ``None`` when the CTF doesn't have enough solves yet. Tied
    timestamps fall back to the database's natural insert order.
    """
    stmt = (
        select(ChallengeSolve.user_id, ChallengeSolve.solved_at)
        .where(ChallengeSolve.challenge_id.in_(
            select(Challenge.id).where(Challenge.ctf_id == ctf_id)
        ))
        .order_by(ChallengeSolve.solved_at, ChallengeSolve.id)
    )
    rows = (await session.execute(stmt)).all()

    first_blood = (rows[0].user_id, rows[0].solved_at) if rows else None
    second_blood = (rows[1].user_id, rows[1].solved_at) if len(rows) > 1 else None

    first_to_milestone = None
    counts: dict[int, int] = {}
    for r in rows:
        counts[r.user_id] = counts.get(r.user_id, 0) + 1
        if counts[r.user_id] == milestone:
            first_to_milestone = (r.user_id, r.solved_at)
            break

    return {
        "first_blood": first_blood,
        "second_blood": second_blood,
        "first_to_milestone": first_to_milestone,
        "milestone": milestone,
    }


async def delete_challenge(
    session: AsyncSession, ctf_id: int, category: str, name: str
) -> Challenge | None:
    """Delete a challenge and its solves. Returns the challenge or None if not found."""
    result = await session.execute(
        select(Challenge).where(
            Challenge.ctf_id == ctf_id,
            Challenge.category == category,
            Challenge.name == name,
        )
    )
    chall = result.scalar_one_or_none()
    if not chall:
        return None
    await session.delete(chall)
    await session.flush()
    return chall
