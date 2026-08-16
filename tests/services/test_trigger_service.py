"""Tests for realm status checks and the remote-start action."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.trigger_service import (
    TriggerError,
    realm_running,
    start_realm,
    verify_pin,
)

_SCREEN_LS_ONE_RUNNING = """There is a screen on:
        12345.gravestone_26_1_2\t(08/16/2026 07:23:00 AM)\t(Detached)
1 Socket in /run/screen/S-minecraft.
"""

_SCREEN_LS_NONE = "No Sockets found in /run/screen/S-minecraft.\n"


def _entry(server_id: str, data_dir: str) -> ServerEntry:
    return ServerEntry(
        server_id=server_id,
        name=server_id.title(),
        status="active",
        port=25565,
        minecraft_version="1.21.10",
        server_type="paper",
        jar_source="",
        data_dir=data_dir,
        created="2026-08-15T21:00:00+00:00",
        notes="",
    )


class _FakeRunner:
    """Records invocations and returns a canned `screen -ls` result."""

    def __init__(self, screen_ls_output: str) -> None:
        self.screen_ls_output = screen_ls_output
        self.calls: list[tuple[list[str], Path | None]] = []

    def __call__(self, args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
        self.calls.append((args, cwd))
        if args[:2] == ["screen", "-ls"]:
            return subprocess.CompletedProcess(args, 0, stdout=self.screen_ls_output, stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


def test_realm_running_true_when_session_present() -> None:
    """A matching screen session name is reported as running."""

    runner = _FakeRunner(_SCREEN_LS_ONE_RUNNING)

    assert realm_running("gravestone_26_1_2", runner=runner) is True


def test_realm_running_false_when_no_match() -> None:
    """A realm with no screen session is reported as not running."""

    runner = _FakeRunner(_SCREEN_LS_ONE_RUNNING)

    assert realm_running("jitterbug_1_21_1", runner=runner) is False


def test_realm_running_false_when_no_sessions_at_all() -> None:
    """No screen sessions at all means nothing is running."""

    runner = _FakeRunner(_SCREEN_LS_NONE)

    assert realm_running("gravestone_26_1_2", runner=runner) is False


def test_start_realm_launches_screen_session(tmp_path: Path) -> None:
    """start_realm invokes screen -dmS with the realm's data_dir as the session name and cwd."""

    runner = _FakeRunner(_SCREEN_LS_NONE)
    entry = _entry("gravestone", "gravestone_26_1_2")

    start_realm(entry, tmp_path, runner=runner)

    start_calls = [call for call in runner.calls if call[0][:2] == ["screen", "-dmS"]]
    assert len(start_calls) == 1
    args, cwd = start_calls[0]
    assert args == ["screen", "-dmS", "gravestone_26_1_2", "./start.sh"]
    assert cwd == tmp_path / "gravestone_26_1_2"


def test_start_realm_refuses_when_already_running(tmp_path: Path) -> None:
    """start_realm raises rather than racing a second screen session for the same realm."""

    runner = _FakeRunner(_SCREEN_LS_ONE_RUNNING)
    entry = _entry("gravestone", "gravestone_26_1_2")

    with pytest.raises(TriggerError):
        start_realm(entry, tmp_path, runner=runner)

    assert not any(call[0][:2] == ["screen", "-dmS"] for call in runner.calls)


def test_verify_pin_matches(tmp_path: Path) -> None:
    """verify_pin accepts the exact PIN in the secret file, trimmed of whitespace."""

    pin_path = tmp_path / "pin.secret"
    pin_path.write_text("4321\n", encoding="utf-8")

    assert verify_pin(pin_path, "4321") is True
    assert verify_pin(pin_path, " 4321 ") is True


def test_verify_pin_rejects_wrong_value(tmp_path: Path) -> None:
    """verify_pin rejects a mismatched PIN."""

    pin_path = tmp_path / "pin.secret"
    pin_path.write_text("4321", encoding="utf-8")

    assert verify_pin(pin_path, "0000") is False


def test_verify_pin_missing_file_rejects() -> None:
    """verify_pin rejects everything if the secret file doesn't exist yet."""

    assert verify_pin(Path("does/not/exist.secret"), "4321") is False
