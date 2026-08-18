"""Tests for reading currently-online usernames from a realm's live log."""

from __future__ import annotations

from pathlib import Path

from minecraftmgr.services.player_service import active_players


def _write_log(logs_dir: Path, lines: list[str]) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "latest.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_active_players_empty_when_no_log_dir(tmp_path: Path) -> None:
    assert active_players(tmp_path / "missing" / "logs") == []


def test_active_players_empty_when_no_join_lines(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    _write_log(logs_dir, ["[10:00:00] [Server thread/INFO]: Starting minecraft server"])

    assert active_players(logs_dir) == []


def test_active_players_includes_joined_with_no_leave(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    _write_log(
        logs_dir,
        ["[10:00:00] [Server thread/INFO]: FourEight1516 joined the game"],
    )

    assert active_players(logs_dir) == ["FourEight1516"]


def test_active_players_excludes_joined_then_left(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    _write_log(
        logs_dir,
        [
            "[10:00:00] [Server thread/INFO]: FourEight1516 joined the game",
            "[10:05:00] [Server thread/INFO]: FourEight1516 left the game",
        ],
    )

    assert active_players(logs_dir) == []


def test_active_players_multiple_online_in_join_order(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    _write_log(
        logs_dir,
        [
            "[10:00:00] [Server thread/INFO]: Mom joined the game",
            "[10:01:00] [Server thread/INFO]: Dad joined the game",
            "[10:02:00] [Server thread/INFO]: Kid joined the game",
            "[10:03:00] [Server thread/INFO]: Dad left the game",
        ],
    )

    assert active_players(logs_dir) == ["Mom", "Kid"]


def test_active_players_leave_without_prior_join_is_ignored(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    _write_log(
        logs_dir,
        ["[10:00:00] [Server thread/INFO]: FourEight1516 left the game"],
    )

    assert active_players(logs_dir) == []


def test_active_players_rejoin_after_leave(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    _write_log(
        logs_dir,
        [
            "[10:00:00] [Server thread/INFO]: FourEight1516 joined the game",
            "[10:05:00] [Server thread/INFO]: FourEight1516 left the game",
            "[10:10:00] [Server thread/INFO]: FourEight1516 joined the game",
        ],
    )

    assert active_players(logs_dir) == ["FourEight1516"]
