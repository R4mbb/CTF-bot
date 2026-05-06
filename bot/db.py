from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.models.base import Base

logger = logging.getLogger(__name__)

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db(database_url: str) -> None:
    global _engine, _session_factory

    # Ensure data directory exists for SQLite
    if "sqlite" in database_url:
        db_path = database_url.split("///")[-1]
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    _engine = create_async_engine(database_url, echo=False)

    # Enable WAL mode for SQLite to prevent "database is locked" errors
    if "sqlite" in database_url:
        @event.listens_for(_engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_patch_missing_columns)

    logger.info("Database initialized: %s", database_url.split("@")[-1] if "@" in database_url else database_url)


def _patch_missing_columns(sync_conn) -> None:
    """Apply lightweight, idempotent column additions for already-existing tables.

    ``Base.metadata.create_all`` does not add new columns to pre-existing tables.
    This bridges the gap for deployments that started before a column was
    introduced, without requiring users to run alembic by hand.
    """
    insp = inspect(sync_conn)
    tables = set(insp.get_table_names())
    if "challenges" in tables:
        cols = {c["name"] for c in insp.get_columns("challenges")}
        if "channel_id" not in cols:
            logger.info("Schema patch: adding challenges.channel_id column")
            sync_conn.execute(text("ALTER TABLE challenges ADD COLUMN channel_id BIGINT"))
    if "ctfs" in tables:
        cols = {c["name"] for c in insp.get_columns("ctfs")}
        if "role_id" not in cols:
            logger.info("Schema patch: adding ctfs.role_id column")
            sync_conn.execute(text("ALTER TABLE ctfs ADD COLUMN role_id BIGINT"))
        if "announcement_message_id" not in cols:
            logger.info("Schema patch: adding ctfs.announcement_message_id column")
            sync_conn.execute(text(
                "ALTER TABLE ctfs ADD COLUMN announcement_message_id BIGINT"
            ))
    if "challenge_solves" in tables:
        # Idempotent unique index works on both SQLite and Postgres. Acts as a
        # de-facto UNIQUE constraint on (challenge_id, user_id). New tables
        # already get the named constraint via create_all; legacy tables get
        # this index instead.
        sync_conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_solve_user_challenge "
            "ON challenge_solves (challenge_id, user_id)"
        ))


async def close_db() -> None:
    global _engine
    if _engine:
        await _engine.dispose()
        logger.info("Database connection closed")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
