"""Tests for the first-boot-then-stop cycle used by provision/activate.

wait_for_ready is tested in full isolation with an injected fake clock so
the tests run instantly regardless of the timeout/poll values under test --
no real time.sleep ever happens.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Callable

import pytest
import yaml

from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.provision_service import (
    ReadinessTimeout,
    RealmCrashedBeforeReady,
    first_boot_cycle,
    patch_velocity_trust,
    wait_for_ready,
)


def _fake_clock(step: float = 1.0) -> Callable[[], float]:
    state = {"t": 0.0}

    def _monotonic() -> float:
        value = state["t"]
        state["t"] += step
        return value

    return _monotonic


def _no_sleep(_seconds: float) -> None:
    return None


def test_wait_for_ready_succeeds_when_marker_present_and_fresh(tmp_path: Path) -> None:
    """A ready marker in a log file written after started_at is trusted."""

    log_path = tmp_path / "latest.log"
    started_at = time.time()
    log_path.write_text("[12:00:00]: Done (1.234s)!\n", encoding="utf-8")
    os.utime(log_path, (started_at + 5, started_at + 5))

    wait_for_ready(
        log_path,
        started_at=started_at,
        still_running=lambda: True,
        sleep=_no_sleep,
        monotonic=_fake_clock(),
    )


def test_wait_for_ready_ignores_stale_log_and_times_out(tmp_path: Path) -> None:
    """A log file older than started_at is never trusted, even with the marker in it.

    This is the exact stale-latest.log bug hit converting jitterbug: an old
    log from a previous run must never be mistaken for the current boot.
    """

    log_path = tmp_path / "latest.log"
    started_at = time.time()
    log_path.write_text("[12:00:00]: Done (1.234s)!\n", encoding="utf-8")
    os.utime(log_path, (started_at - 100, started_at - 100))

    with pytest.raises(ReadinessTimeout):
        wait_for_ready(
            log_path,
            started_at=started_at,
            still_running=lambda: True,
            timeout_seconds=3,
            poll_interval=1,
            sleep=_no_sleep,
            monotonic=_fake_clock(),
        )


def test_wait_for_ready_raises_timeout_when_marker_never_appears(tmp_path: Path) -> None:
    """No marker ever appearing raises ReadinessTimeout, not a silent hang."""

    log_path = tmp_path / "latest.log"

    with pytest.raises(ReadinessTimeout):
        wait_for_ready(
            log_path,
            started_at=time.time(),
            still_running=lambda: True,
            timeout_seconds=3,
            poll_interval=1,
            sleep=_no_sleep,
            monotonic=_fake_clock(),
        )


def test_wait_for_ready_fails_fast_when_process_exits_before_ready(tmp_path: Path) -> None:
    """The process dying before the marker appears raises immediately, not after the full timeout."""

    log_path = tmp_path / "latest.log"
    calls = {"n": 0}

    def _still_running() -> bool:
        calls["n"] += 1
        return calls["n"] < 2  # running on first check, dead on the second

    with pytest.raises(RealmCrashedBeforeReady):
        wait_for_ready(
            log_path,
            started_at=time.time(),
            still_running=_still_running,
            timeout_seconds=300,
            poll_interval=1,
            sleep=_no_sleep,
            monotonic=_fake_clock(),
        )


def _entry(server_id: str, data_dir: str) -> ServerEntry:
    return ServerEntry(
        server_id=server_id,
        name=server_id.title(),
        status="active",
        port=26020,
        minecraft_version="1.21.10",
        server_type="paper",
        jar_source="",
        data_dir=data_dir,
        created="2026-08-16T21:00:00+00:00",
        notes="",
    )


class _BootRunner:
    """Fake runner simulating a realm that starts, becomes ready, then stops gracefully."""

    def __init__(self, data_dir: str, log_path: Path) -> None:
        self.data_dir = data_dir
        self.log_path = log_path
        self.started = False
        self.stopped = False

    def __call__(self, args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
        if args[:2] == ["screen", "-ls"]:
            running = self.started and not self.stopped
            output = f"There is a screen on:\n        1.{self.data_dir}\t(date)\t(Detached)\n" if running else "No Sockets found.\n"
            return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

        if args[:2] == ["screen", "-dmS"]:
            self.started = True
            started_at = time.time()
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.write_text("[12:00:00]: Done (1.0s)!\n", encoding="utf-8")
            os.utime(self.log_path, (started_at + 1, started_at + 1))
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        if args[:2] == ["screen", "-S"] and "stuff" in args:
            self.stopped = True
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


def test_first_boot_cycle_starts_waits_then_stops(tmp_path: Path) -> None:
    """The happy path: start -> ready -> graceful stop, returns the paper-global.yml path."""

    entry = _entry("gatorland", "gatorland_26_2")
    log_path = tmp_path / "gatorland_26_2" / "logs" / "latest.log"
    runner = _BootRunner("gatorland_26_2", log_path)

    result = first_boot_cycle(entry, tmp_path, runner=runner, sleep=_no_sleep)

    assert result == tmp_path / "gatorland_26_2" / "config" / "paper-global.yml"
    assert runner.started is True
    assert runner.stopped is True


def test_patch_velocity_trust_raises_if_file_missing(tmp_path: Path) -> None:
    """Patching before a first boot has generated the file is refused, not silently created."""

    with pytest.raises(FileNotFoundError):
        patch_velocity_trust(tmp_path / "config" / "paper-global.yml", "s3cret")


def test_patch_velocity_trust_sets_trust_fields(tmp_path: Path) -> None:
    """enabled/online-mode/secret are set correctly under proxies.velocity."""

    paper_global = tmp_path / "paper-global.yml"
    paper_global.write_text("_version: 30\nproxies:\n  velocity:\n    enabled: false\n", encoding="utf-8")

    patch_velocity_trust(paper_global, "s3cret", online_mode=True)


    data = yaml.safe_load(paper_global.read_text(encoding="utf-8"))
    assert data["proxies"]["velocity"]["enabled"] is True
    assert data["proxies"]["velocity"]["online-mode"] is True
    assert data["proxies"]["velocity"]["secret"] == "s3cret"


def test_patch_velocity_trust_preserves_other_top_level_keys(tmp_path: Path) -> None:
    """Unrelated top-level settings already in the file survive the patch."""

    paper_global = tmp_path / "paper-global.yml"
    paper_global.write_text("_version: 30\nother-setting: 42\n", encoding="utf-8")

    patch_velocity_trust(paper_global, "s3cret")


    data = yaml.safe_load(paper_global.read_text(encoding="utf-8"))
    assert data["_version"] == 30
    assert data["other-setting"] == 42
    assert data["proxies"]["velocity"]["secret"] == "s3cret"
