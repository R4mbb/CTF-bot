"""Tests for CTFTime integration parsing."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bot.integrations.ctftime import CTFTimeClient, CTFTimeEvent


def test_cache_logic():
    client = CTFTimeClient(cache_ttl=1800)
    assert client._is_cached("test") is False

    events = [
        CTFTimeEvent(
            id=1, title="Test", url="http://test.com",
            ctftime_url="https://ctftime.org/event/1",
            start=datetime(2025, 1, 1, tzinfo=timezone.utc),
            finish=datetime(2025, 1, 2, tzinfo=timezone.utc),
            format="Jeopardy", weight=50.0, description="A test CTF",
        )
    ]
    client._set_cache("test", events)
    assert client._is_cached("test") is True
    assert len(client._get_cached("test")) == 1


def test_ctftime_event_dataclass():
    ev = CTFTimeEvent(
        id=42, title="HackTheBox CTF",
        url="https://ctf.hackthebox.com",
        ctftime_url="https://ctftime.org/event/42",
        start=datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc),
        finish=datetime(2025, 6, 2, 12, 0, tzinfo=timezone.utc),
        format="Jeopardy",
        weight=75.5,
        description="A great CTF",
    )
    assert ev.id == 42
    assert ev.weight == 75.5
