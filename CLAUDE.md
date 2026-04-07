# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CTF team management Discord bot (Korean CTF team). Manages CTF lifecycle, team registration, challenge tracking, and CTFTime integration. All UI text mixes Korean labels with English values.

## Commands

```bash
# Run locally
source .venv/bin/activate
python -m bot.main

# Run with Docker
docker compose up --build -d

# Tests
pip install -r requirements-dev.txt
pytest tests/ -v
pytest tests/test_ctf_service.py -v -k "test_create"  # single test

# DB migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

## Architecture

**Layered design**: Cogs (slash commands) → Services (business logic + Discord ops) → Models (SQLAlchemy ORM) → async SQLite/PostgreSQL.

- `bot/main.py` — `CTFBot` subclass, loads cogs + scheduler in `setup_hook()`
- `bot/config.py` — Frozen dataclass, all settings from env vars
- `bot/db.py` — Async SQLAlchemy engine + `get_session()` context manager (WAL mode for SQLite)
- `bot/scheduler.py` — APScheduler: auto-archive ended CTFs (interval), weekly CTFTime digest (cron Mon 09:00 KST)
- `bot/cogs/admin.py` — Admin commands (`/create_ctf`, `/delete_ctf`, `/create_ctf_from_ctftime`). Contains `CreateCTFModal`, `JoinCTFView`, `ConfirmDeleteView` UI components
- `bot/cogs/user.py` — User commands (`/init`, `/join_ctf`, `/add_challenge`, `/solve_challenge`, etc.). Contains `InitModal` for team registration
- `bot/cogs/ctftime_cog.py` — CTFTime commands, uses cached `CTFTimeClient`
- `bot/services/ctf_service.py` — All DB operations (CTF CRUD, membership, challenges)
- `bot/services/discord_service.py` — Discord resource management (categories, channels, permissions, init channels)
- `bot/services/audit.py` — DB audit logging
- `bot/services/discord_log.py` — Activity feed to #logs channel
- `bot/integrations/ctftime.py` — `CTFTimeClient` with in-memory cache + httpx
- `bot/utils/embeds.py` — All Discord embed builders (themed with status colors, progress bars)
- `bot/utils/permissions.py` — `is_admin()` / `admin_check()` helpers

## Key Patterns

- **Permission model**: Category-level overwrites cascade to channels. CTF categories hidden by default; `grant_user_access()` adds per-user overwrites on join
- **CTF lifecycle**: Create → Join → Active → Ended → Auto-archive (scheduler makes public/read-only)
- **Soft deletes**: CTFs use `deleted=True` flag, never hard-deleted from DB
- **Challenge channels**: Named `{category}-{name}`, renamed to `✅-{name}` on solve
- **Member onboarding**: `on_member_join` → private `#init-{username}` channel → `/init` modal → assigns team role → deletes init channel
- **Tests use in-memory SQLite** via `conftest.py` fixtures; `asyncio_mode = "auto"` in pyproject.toml

## Environment

Requires `DISCORD_TOKEN` and `DISCORD_APP_ID`. See README.md for full env var table. Default DB is `sqlite+aiosqlite:///./data/ctfbot.db`.
