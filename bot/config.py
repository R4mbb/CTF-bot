from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    discord_token: str = field(repr=False, default_factory=lambda: os.environ["DISCORD_TOKEN"])
    discord_app_id: str = field(default_factory=lambda: os.environ["DISCORD_APP_ID"])
    dev_guild_id: int | None = field(
        default_factory=lambda: int(g) if (g := os.getenv("DEV_GUILD_ID")) else None
    )
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/ctfbot.db")
    )
    admin_role_name: str = field(
        default_factory=lambda: os.getenv("ADMIN_ROLE_NAME", "CTF Admin")
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    timezone: str = field(default_factory=lambda: os.getenv("TIMEZONE", "UTC"))
    ctftime_cache_ttl: int = field(
        default_factory=lambda: int(os.getenv("CTFTIME_CACHE_TTL", "1800"))
    )
    scheduler_interval_minutes: int = field(
        default_factory=lambda: int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "5"))
    )

    # Channel name for weekly CTFTime digest (Mon 09:00 KST)
    announcement_channel: str = field(
        default_factory=lambda: os.getenv("ANNOUNCEMENT_CHANNEL", "ctf-일정")
    )

    # Default channels created inside every CTF category
    default_channels: list[str] = field(default_factory=lambda: [
        "announcements",
        "general",
        "writeups",
        "scoreboard",
        "challenge-log",
    ])
