"""Tests for the ScreenshotMatch model."""

from __future__ import annotations

from datetime import datetime

from minecraftmgr.models.screenshot_match import ScreenshotMatch


def test_round_trip_matched_entry() -> None:
    """A matched entry survives a to_dict/from_dict round trip."""

    match = ScreenshotMatch(
        filename="2026-08-17_14.32.10.png",
        taken_at=datetime(2026, 8, 17, 14, 32, 10),
        realm="gravestone",
        minecraft_version="26.1.2",
        relative_path="gravestone/26.1.2/2026-08-17_14.32.10.png",
        matched=True,
    )

    restored = ScreenshotMatch.from_dict(match.to_dict())

    assert restored == match


def test_round_trip_unmatched_entry_has_no_timestamp() -> None:
    """An unmatched entry with no parsed timestamp round-trips taken_at as None."""

    match = ScreenshotMatch(
        filename="random.png",
        taken_at=None,
        realm=None,
        minecraft_version=None,
        relative_path="_unsorted/random.png",
        matched=False,
    )

    restored = ScreenshotMatch.from_dict(match.to_dict())

    assert restored == match
    assert restored.taken_at is None
