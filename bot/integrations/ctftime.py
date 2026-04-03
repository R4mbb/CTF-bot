"""CTFTime.org API integration with simple in-memory cache."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

CTFTIME_API = "https://ctftime.org/api/v1/events/"
USER_AGENT = "CTFBot/1.0 (Discord Bot)"


@dataclass
class CTFTimeEvent:
    id: int
    title: str
    url: str
    ctftime_url: str
    start: datetime
    finish: datetime
    format: str
    weight: float
    description: str


class CTFTimeClient:
    def __init__(self, cache_ttl: int = 1800):
        self._cache: dict[str, tuple[float, list[CTFTimeEvent]]] = {}
        self._cache_ttl = cache_ttl
        # Stores the last week-fetched events for quick-create by number
        self.last_week_events: list[CTFTimeEvent] = []

    def _is_cached(self, key: str) -> bool:
        if key not in self._cache:
            return False
        ts, _ = self._cache[key]
        return (time.monotonic() - ts) < self._cache_ttl

    def _get_cached(self, key: str) -> list[CTFTimeEvent]:
        return self._cache[key][1]

    def _set_cache(self, key: str, data: list[CTFTimeEvent]) -> None:
        self._cache[key] = (time.monotonic(), data)

    async def fetch_upcoming(self, days: int) -> list[CTFTimeEvent]:
        cache_key = f"upcoming_{days}"
        if self._is_cached(cache_key):
            return self._get_cached(cache_key)

        now = datetime.now(timezone.utc)
        start = int(now.timestamp())
        finish = int((now + timedelta(days=days)).timestamp())

        params = {"limit": 50, "start": start, "finish": finish}
        events = await self._request(params)
        self._set_cache(cache_key, events)
        return events

    async def fetch_week(self) -> list[CTFTimeEvent]:
        events = await self.fetch_upcoming(7)
        self.last_week_events = events
        return events

    async def fetch_month(self) -> list[CTFTimeEvent]:
        return await self.fetch_upcoming(30)

    def get_event_by_number(self, number: int) -> CTFTimeEvent | None:
        """Get an event from the last week fetch by its 1-based display number."""
        idx = number - 1
        if 0 <= idx < len(self.last_week_events):
            return self.last_week_events[idx]
        return None

    async def _request(self, params: dict) -> list[CTFTimeEvent]:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    CTFTIME_API,
                    params=params,
                    headers={"User-Agent": USER_AGENT},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.error("CTFTime API error: %s", exc)
            return []
        except Exception as exc:
            logger.error("CTFTime unexpected error: %s", exc)
            return []

        events: list[CTFTimeEvent] = []
        for item in data:
            try:
                events.append(CTFTimeEvent(
                    id=item["id"],
                    title=item["title"],
                    url=item.get("url", ""),
                    ctftime_url=item.get("ctftime_url", f"https://ctftime.org/event/{item['id']}"),
                    start=datetime.fromisoformat(item["start"]),
                    finish=datetime.fromisoformat(item["finish"]),
                    format=item.get("format", ""),
                    weight=item.get("weight", 0.0),
                    description=item.get("description", "")[:200],
                ))
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed CTFTime event: %s", exc)
        return events
