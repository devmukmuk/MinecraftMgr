"""Tests for the screenshot matcher service."""

from __future__ import annotations

import gzip
from datetime import datetime, timedelta
from pathlib import Path

from minecraftmgr.services.screenshot_matcher_service import (
    RealmSession,
    build_realm_sessions,
    load_manifest,
    match_realm,
    organize_screenshots,
    parse_screenshot_timestamp,
    write_manifest,
)


def test_parse_screenshot_timestamp_valid_name() -> None:
    """Minecraft's own screenshot filename format parses to a datetime."""

    expected = datetime(2026, 8, 17, 14, 32, 10)
    assert parse_screenshot_timestamp("2026-08-17_14.32.10.png") == expected


def test_parse_screenshot_timestamp_tolerates_duplicate_suffix() -> None:
    """A Windows-appended ' (1)' duplicate suffix doesn't break the prefix match."""

    expected = datetime(2026, 8, 17, 14, 32, 10)
    assert parse_screenshot_timestamp("2026-08-17_14.32.10 (1).png") == expected


def test_parse_screenshot_timestamp_unrecognized_name_returns_none() -> None:
    """A filename that isn't Minecraft's own format returns None instead of raising."""

    assert parse_screenshot_timestamp("Screenshot 2025-09-30 115705.png") is None


def _write_log(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_gz_log(path: Path, lines: list[str]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def test_build_realm_sessions_pairs_join_and_leave(tmp_path: Path) -> None:
    """A join followed by a leave in the same log file becomes one closed session."""

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_log(
        logs_dir / "2026-08-17-1.log",
        [
            "[14:32:05] [Server thread/INFO]: MikeM joined the game",
            "[15:10:00] [Server thread/INFO]: MikeM left the game",
        ],
    )

    sessions = build_realm_sessions(logs_dir, "MikeM")

    assert sessions == [
        RealmSession(datetime(2026, 8, 17, 14, 32, 5), datetime(2026, 8, 17, 15, 10, 0))
    ]


def test_build_realm_sessions_open_session_has_no_end(tmp_path: Path) -> None:
    """A join with no matching leave anywhere stays open (end=None)."""

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_log(
        logs_dir / "2026-08-17-1.log",
        ["[14:32:05] [Server thread/INFO]: MikeM joined the game"],
    )

    sessions = build_realm_sessions(logs_dir, "MikeM")

    assert sessions == [RealmSession(datetime(2026, 8, 17, 14, 32, 5), None)]


def test_build_realm_sessions_spans_log_rotation(tmp_path: Path) -> None:
    """A join in one (gzipped) log file and a leave in the next still form one session."""

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_gz_log(
        logs_dir / "2026-08-17-1.log.gz",
        ["[23:58:00] [Server thread/INFO]: MikeM joined the game"],
    )
    _write_log(
        logs_dir / "2026-08-18-1.log",
        ["[00:15:00] [Server thread/INFO]: MikeM left the game"],
    )

    sessions = build_realm_sessions(logs_dir, "MikeM")

    assert sessions == [
        RealmSession(datetime(2026, 8, 17, 23, 58, 0), datetime(2026, 8, 18, 0, 15, 0))
    ]


def test_build_realm_sessions_ignores_other_usernames(tmp_path: Path) -> None:
    """Join/leave lines for a different player don't produce a session."""

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_log(
        logs_dir / "2026-08-17-1.log",
        [
            "[14:32:05] [Server thread/INFO]: SomeoneElse joined the game",
            "[15:10:00] [Server thread/INFO]: SomeoneElse left the game",
        ],
    )

    assert not build_realm_sessions(logs_dir, "MikeM")


def test_match_realm_picks_the_containing_session() -> None:
    """A timestamp inside a realm's session window matches that realm."""

    realm_sessions = {
        "gravestone": [RealmSession(datetime(2026, 8, 17, 14, 0), datetime(2026, 8, 17, 15, 0))],
        "cave": [RealmSession(datetime(2026, 8, 17, 16, 0), datetime(2026, 8, 17, 17, 0))],
    }

    assert match_realm(datetime(2026, 8, 17, 14, 30), realm_sessions) == "gravestone"
    assert match_realm(datetime(2026, 8, 17, 16, 30), realm_sessions) == "cave"


def test_match_realm_outside_any_window_returns_none() -> None:
    """A timestamp outside every session window (even with slack) matches nothing."""

    realm_sessions = {
        "gravestone": [RealmSession(datetime(2026, 8, 17, 14, 0), datetime(2026, 8, 17, 15, 0))],
    }

    assert match_realm(datetime(2026, 8, 17, 20, 0), realm_sessions, timedelta(seconds=5)) is None


def test_match_realm_applies_slack_at_boundary() -> None:
    """A timestamp just past a session's end is still matched within slack tolerance."""

    realm_sessions = {
        "gravestone": [RealmSession(datetime(2026, 8, 17, 14, 0), datetime(2026, 8, 17, 15, 0))],
    }

    slightly_late = datetime(2026, 8, 17, 15, 0, 3)
    assert match_realm(slightly_late, realm_sessions, timedelta(seconds=5)) == "gravestone"


def test_organize_screenshots_sorts_matched_and_unsorted(tmp_path: Path) -> None:
    """Screenshots move into <realm>/<version>/ when matched, or _unsorted/ otherwise."""

    data_root = tmp_path / "data"
    gravestone_logs = data_root / "gravestone_26_1_2" / "logs"
    gravestone_logs.mkdir(parents=True)
    _write_log(
        gravestone_logs / "2026-08-17-1.log",
        [
            "[14:00:00] [Server thread/INFO]: MikeM joined the game",
            "[15:00:00] [Server thread/INFO]: MikeM left the game",
        ],
    )

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "2026-08-17_14.30.00.png").write_bytes(b"fake-png-matched")
    (inbox / "2026-08-17_20.00.00.png").write_bytes(b"fake-png-outside-session")
    (inbox / "not-a-screenshot.txt").write_text("ignore me", encoding="utf-8")

    output_root = tmp_path / "_screenshots"
    realm_logs = {"gravestone": (gravestone_logs, "26.1.2")}

    matches = organize_screenshots(inbox, output_root, realm_logs, "MikeM")

    assert len(matches) == 2

    matched = next(m for m in matches if m.matched)
    unmatched = next(m for m in matches if not m.matched)

    assert matched.realm == "gravestone"
    assert matched.minecraft_version == "26.1.2"
    assert (output_root / "gravestone" / "26.1.2" / "2026-08-17_14.30.00.png").exists()

    assert unmatched.realm is None
    assert (output_root / "_unsorted" / "2026-08-17_20.00.00.png").exists()

    assert not (inbox / "2026-08-17_14.30.00.png").exists()
    assert (inbox / "not-a-screenshot.txt").exists()


def test_organize_screenshots_missing_inbox_returns_empty(tmp_path: Path) -> None:
    """A missing inbox directory is treated as zero screenshots, not an error."""

    matches = organize_screenshots(
        tmp_path / "does-not-exist", tmp_path / "out", {}, "MikeM"
    )

    assert not matches


def test_manifest_round_trip(tmp_path: Path) -> None:
    """write_manifest followed by load_manifest returns equivalent matches."""

    data_root = tmp_path / "data"
    gravestone_logs = data_root / "gravestone_26_1_2" / "logs"
    gravestone_logs.mkdir(parents=True)
    _write_log(
        gravestone_logs / "2026-08-17-1.log",
        [
            "[14:00:00] [Server thread/INFO]: MikeM joined the game",
            "[15:00:00] [Server thread/INFO]: MikeM left the game",
        ],
    )

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "2026-08-17_14.30.00.png").write_bytes(b"fake-png")

    output_root = tmp_path / "_screenshots"
    matches = organize_screenshots(
        inbox, output_root, {"gravestone": (gravestone_logs, "26.1.2")}, "MikeM"
    )

    manifest_path = write_manifest(matches, output_root / "manifest.json")
    reloaded = load_manifest(manifest_path)

    assert reloaded == matches


def test_load_manifest_missing_file_returns_empty(tmp_path: Path) -> None:
    """Loading a manifest that doesn't exist yet returns an empty list."""

    assert load_manifest(tmp_path / "manifest.json") == []
