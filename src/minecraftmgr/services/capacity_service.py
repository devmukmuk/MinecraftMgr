"""Enforce a cap on concurrently-running realms, evicting an idle one on demand.

Deliberately reactive, not proactive: a realm only ever gets stopped here
because starting a *different* realm needed the room, never on a timer just
because it happened to be idle. Oscar has 15Gi total RAM -- see the
`realm validate`/`-Xmx14G` incident (PROV-design.md) for why running
everything registered at once isn't safe.

Idle is determined by counting established TCP connections to a realm's own
backend port via `ss`, not RCON (disabled on every realm today) and not a
Minecraft protocol client (same fidelity, more code to maintain). Works
whether or not the realm sits behind Velocity -- Velocity keeps one backend
connection open per connected player, so the count is accurate either way.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable

from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.trigger_service import realm_running, start_realm, stop_realm

CommandRunner = Callable[..., "subprocess.CompletedProcess[str]"]


class CapacityError(Exception):
    """Raised when at capacity and no running realm is idle to evict."""


def _default_runner(args: list[str], cwd: Path | None = None) -> "subprocess.CompletedProcess[str]":
    """Matches trigger_service's own default runner shape (accepts cwd) so the same
    injected runner can drive both realm_running/start_realm/stop_realm and ss here."""

    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


def connected_player_count(port: int, *, runner: CommandRunner = _default_runner) -> int:
    """Count established TCP connections to a realm's backend port.

    `ss` always prints its own header line even with zero matches, so the
    connection count is one less than the line count.
    """

    result = runner(["ss", "-tn", "state", "established", "sport", "=", f":{port}"])
    lines = [line for line in result.stdout.splitlines() if line.strip()]

    return max(0, len(lines) - 1)


def is_idle(server: ServerEntry, *, runner: CommandRunner = _default_runner) -> bool:
    """A realm is idle if nothing is currently connected to its backend port."""

    return connected_player_count(server.port, runner=runner) == 0


def find_idle_running_realm(
    candidates: list[ServerEntry],
    *,
    exclude: set[str] = frozenset(),
    runner: CommandRunner = _default_runner,
) -> ServerEntry | None:
    """Return the first candidate that's running and idle, skipping excluded ids."""

    for server in candidates:
        if server.server_id in exclude:
            continue
        if realm_running(server.data_dir, runner=runner) and is_idle(server, runner=runner):
            return server

    return None


def start_realm_within_capacity(
    server: ServerEntry,
    all_servers: list[ServerEntry],
    data_root: Path,
    *,
    max_running: int,
    exclude_from_eviction: set[str] = frozenset(),
    runner: CommandRunner = _default_runner,
    sleep: Callable[[float], None] = time.sleep,
) -> ServerEntry | None:
    """Start a realm, evicting one idle realm first if already at capacity.

    Returns the evicted realm, if any, so callers can report what happened.
    Raises CapacityError if at capacity and nothing eligible is idle --
    never silently fails to start, and never evicts something outside the
    caller's control without saying so.
    """

    running = [
        candidate for candidate in all_servers if realm_running(candidate.data_dir, runner=runner)
    ]

    evicted: ServerEntry | None = None

    if len(running) >= max_running:
        idle = find_idle_running_realm(running, exclude=exclude_from_eviction, runner=runner)

        if idle is None:
            raise CapacityError(
                f"{max_running} realms already running and none are idle -- try again shortly"
            )

        stop_realm(idle, data_root, runner=runner, sleep=sleep)
        evicted = idle

    start_realm(server, data_root, runner=runner)

    return evicted
