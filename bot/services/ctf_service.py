"""Business logic for CTF operations (DB layer)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
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


async def list_ctfs(session: AsyncSession, guild_id: int, include_deleted: bool = False) -> list[CTF]:
    stmt = select(CTF).where(CTF.guild_id == guild_id)
    if not include_deleted:
        stmt = stmt.where(CTF.deleted == False)
    stmt = stmt.order_by(CTF.start_time.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def soft_delete_ctf(session: AsyncSession, ctf: CTF) -> None:
    ctf.deleted = True


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
    """Return Challenge or None if duplicate."""
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
    session.add(chall)
    await session.flush()
    return chall


async def solve_challenge(
    session: AsyncSession,
    *,
    challenge_id: int,
    user_id: int,
    flag: str | None = None,
    writeup_url: str | None = None,
    notes: str | None = None,
) -> ChallengeSolve:
    solve = ChallengeSolve(
        challenge_id=challenge_id,
        user_id=user_id,
        flag=flag,
        writeup_url=writeup_url,
        notes=notes,
    )
    session.add(solve)

    # Mark challenge as solved
    stmt = select(Challenge).where(Challenge.id == challenge_id)
    result = await session.execute(stmt)
    chall = result.scalar_one()
    chall.solved = True

    await session.flush()
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
