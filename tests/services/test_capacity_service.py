"""Tests for the concurrently-running-realm cap and on-demand idle eviction."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.capacity_service import (
    CapacityError,
    connected_player_count,
    find_idle_running_realm,
    is_idle,
    start_realm_within_capacity,
)

_SS_HEADER = "Recv-Q Send-Q          Local Address:Port          Peer Address:Port Process\n"
_SS_ONE_CONNECTION = (
    _SS_HEADER + "0      0              192.168.1.113:26005       192.168.1.81:64411        \n"
)
_SS_NONE = _SS_HEADER


def _entry(server_id: str, data_dir: str, port: int) -> ServerEntry:
    return ServerEntry(
        server_id=server_id,
        name=server_id.title(),
        status="active",
        port=port,
        minecraft_version="1.21.10",
        server_type="paper",
        jar_source="",
        data_dir=data_dir,
        created="2026-08-15T21:00:00+00:00",
        notes="",
    )


def _no_sleep(_seconds: float) -> None:
    return None


class _FakeRunner:
    """Stateful: screen -dmS/-X stuff update running_data_dirs immediately, so
    stop_realm()'s poll loop sees the change on its very first check instead
    of running out a real wait_seconds timeout -- same reasoning as
    test_trigger_service.py's _StatefulRunner."""

    def __init__(
        self,
        running_data_dirs: set[str],
        connected_ports: set[int],
    ) -> None:
        self.running_data_dirs = set(running_data_dirs)
        self.connected_ports = set(connected_ports)
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
        self.calls.append(list(args))

        if args[:2] == ["screen", "-ls"]:
            lines = "".join(f"\t12345.{name}\t(Detached)\n" for name in self.running_data_dirs)
            output = f"There is a screen on:\n{lines}" if lines else "No Sockets found.\n"
            return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

        if args[:2] == ["screen", "-dmS"]:
            self.running_data_dirs.add(args[2])
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        if args[:2] == ["screen", "-S"] and "stuff" in args:
            self.running_data_dirs.discard(args[2])
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        if args[:4] == ["ss", "-tn", "state", "established"]:
            port = int(args[-1].lstrip(":"))
            output = _SS_ONE_CONNECTION if port in self.connected_ports else _SS_NONE
            return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")

        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


def test_connected_player_count_zero_when_no_matching_lines() -> None:
    """An empty ss result (just the header) means zero connections."""

    runner = _FakeRunner(running_data_dirs=set(), connected_ports=set())

    assert connected_player_count(26005, runner=runner) == 0


def test_connected_player_count_counts_non_header_lines() -> None:
    """One real connection line beyond the header counts as one player."""

    runner = _FakeRunner(running_data_dirs=set(), connected_ports={26005})

    assert connected_player_count(26005, runner=runner) == 1


def test_is_idle_true_when_zero_connections(tmp_path: Path) -> None:
    server = _entry("gravestone", "gravestone_26_1_2", port=26005)
    runner = _FakeRunner(running_data_dirs=set(), connected_ports=set())

    assert is_idle(server, runner=runner) is True


def test_is_idle_false_when_connections_present(tmp_path: Path) -> None:
    server = _entry("gravestone", "gravestone_26_1_2", port=26005)
    runner = _FakeRunner(running_data_dirs=set(), connected_ports={26005})

    assert is_idle(server, runner=runner) is False


def test_find_idle_running_realm_skips_stopped_and_busy(tmp_path: Path) -> None:
    """Only a realm that is both running AND idle qualifies as an eviction candidate."""

    busy = _entry("gravestone", "gravestone_26_1_2", port=26005)
    idle = _entry("jitterbug", "jitterbug_1_21_1", port=26887)
    stopped = _entry("arbor", "arbor_1_21_10", port=26124)

    runner = _FakeRunner(
        running_data_dirs={"gravestone_26_1_2", "jitterbug_1_21_1"},
        connected_ports={26005},  # gravestone busy, jitterbug idle, arbor not even running
    )

    result = find_idle_running_realm([busy, idle, stopped], runner=runner)

    assert result is idle


def test_find_idle_running_realm_respects_exclude(tmp_path: Path) -> None:
    """A realm excluded from eviction is never returned, even if it's idle and running."""

    idle_but_excluded = _entry("jitterbug", "jitterbug_1_21_1", port=26887)

    runner = _FakeRunner(running_data_dirs={"jitterbug_1_21_1"}, connected_ports=set())

    result = find_idle_running_realm(
        [idle_but_excluded], exclude={"jitterbug"}, runner=runner
    )

    assert result is None


def test_start_within_capacity_no_eviction_when_room_available(tmp_path: Path) -> None:
    """Starting a realm when under the cap never touches any other realm."""

    target = _entry("river", "river_1_21_1", port=26010)
    already_running = _entry("gravestone", "gravestone_26_1_2", port=26005)

    runner = _FakeRunner(running_data_dirs={"gravestone_26_1_2"}, connected_ports={26005})

    evicted = start_realm_within_capacity(
        target, [target, already_running], tmp_path, max_running=3, runner=runner
    )

    assert evicted is None
    assert not any(call[:2] == ["screen", "-S"] for call in runner.calls)  # no stop sent
    assert any(call[:2] == ["screen", "-dmS"] for call in runner.calls)  # start sent


def test_start_within_capacity_evicts_idle_realm_when_full(tmp_path: Path) -> None:
    """At capacity, the idle realm is stopped first, then the target is started."""

    target = _entry("poop", "poop_1_21_1", port=26314)
    busy = _entry("gravestone", "gravestone_26_1_2", port=26005)
    idle = _entry("jitterbug", "jitterbug_1_21_1", port=26887)
    other_busy = _entry("cave", "cave_1_21_1", port=26913)

    runner = _FakeRunner(
        running_data_dirs={"gravestone_26_1_2", "jitterbug_1_21_1", "cave_1_21_1"},
        connected_ports={26005, 26913},  # gravestone + cave busy, jitterbug idle
    )

    evicted = start_realm_within_capacity(
        target,
        [target, busy, idle, other_busy],
        tmp_path,
        max_running=3,
        runner=runner,
        sleep=_no_sleep,
    )

    assert evicted is idle
    stop_calls = [call for call in runner.calls if call[:2] == ["screen", "-S"]]
    assert any("jitterbug_1_21_1" in call for call in stop_calls)
    assert any(call[:2] == ["screen", "-dmS"] for call in runner.calls)


def test_start_within_capacity_raises_when_full_and_nothing_idle(tmp_path: Path) -> None:
    """At capacity with every running realm busy, the start is refused, not silently skipped."""

    target = _entry("poop", "poop_1_21_1", port=26314)
    busy_a = _entry("gravestone", "gravestone_26_1_2", port=26005)
    busy_b = _entry("cave", "cave_1_21_1", port=26913)
    busy_c = _entry("river", "river_1_21_1", port=26010)

    runner = _FakeRunner(
        running_data_dirs={"gravestone_26_1_2", "cave_1_21_1", "river_1_21_1"},
        connected_ports={26005, 26913, 26010},
    )

    with pytest.raises(CapacityError):
        start_realm_within_capacity(
            target, [target, busy_a, busy_b, busy_c], tmp_path, max_running=3, runner=runner
        )

    assert not any(call[:2] == ["screen", "-dmS"] for call in runner.calls)


def test_start_within_capacity_exclude_from_eviction_prevents_batch_flapping(tmp_path: Path) -> None:
    """--all shouldn't evict one batch member just to start another -- that's just flapping."""

    target = _entry("poop", "poop_1_21_1", port=26314)
    batch_mate_idle = _entry("river", "river_1_21_1", port=26010)  # also wanted, idle, excluded
    busy_a = _entry("gravestone", "gravestone_26_1_2", port=26005)
    busy_b = _entry("cave", "cave_1_21_1", port=26913)

    runner = _FakeRunner(
        running_data_dirs={"gravestone_26_1_2", "cave_1_21_1", "river_1_21_1"},
        connected_ports={26005, 26913},  # river is idle but excluded
    )

    with pytest.raises(CapacityError):
        start_realm_within_capacity(
            target,
            [target, batch_mate_idle, busy_a, busy_b],
            tmp_path,
            max_running=3,
            exclude_from_eviction={"poop", "river"},
            runner=runner,
        )
