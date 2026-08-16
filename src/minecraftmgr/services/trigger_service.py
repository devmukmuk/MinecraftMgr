"""Realm status checks and the remote start/stop actions used by the trigger
daemon and realm provisioning.

Kept free of any HTTP/network concerns so it can be unit tested without a
live `screen` install -- callers inject a `runner` in tests.
"""

from __future__ import annotations

import hmac
import re
import subprocess
import time
from pathlib import Path
from typing import Callable

from minecraftmgr.models.server_entry import ServerEntry

CommandRunner = Callable[..., "subprocess.CompletedProcess[str]"]


class TriggerError(Exception):
    """Raised when a realm can't be started."""


def _default_runner(args: list[str], cwd: Path | None = None) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


def realm_running(data_dir: str, *, runner: CommandRunner = _default_runner) -> bool:
    """Return whether a screen session for this realm's data dir is currently up."""

    result = runner(["screen", "-ls"])
    return bool(re.search(rf"\.{re.escape(data_dir)}\s", result.stdout))


def start_realm(
    server: ServerEntry,
    data_root: Path,
    *,
    runner: CommandRunner = _default_runner,
) -> None:
    """Start a realm's screen session by running its start.sh in its data directory.

    Refuses to start a realm that already has a screen session up, since a
    second `screen -dmS` with the same name races the existing process
    rather than replacing it.
    """

    if realm_running(server.data_dir, runner=runner):
        raise TriggerError(f"'{server.server_id}' is already running")

    realm_dir = data_root / server.data_dir
    runner(["screen", "-dmS", server.data_dir, "./start.sh"], cwd=realm_dir)


def _kill_matching_processes(data_dir: str, *, runner: CommandRunner) -> None:
    """Fallback: find and kill both the screen wrapper and java process for this realm."""

    result = runner(["pgrep", "-f", data_dir])
    pids = [line.strip() for line in result.stdout.splitlines() if line.strip()]

    if pids:
        runner(["kill", *pids])


def stop_realm(
    server: ServerEntry,
    data_root: Path,
    *,
    runner: CommandRunner = _default_runner,
    sleep: Callable[[float], None] = time.sleep,
    wait_seconds: float = 10,
    poll_interval: float = 1,
) -> None:
    """Stop a realm's screen session gracefully, falling back to pgrep+kill if it doesn't take.

    Sends the in-game `stop` command via `screen -X stuff`, then polls
    realm_running() for up to wait_seconds. screen's `stuff` doesn't always
    reach the console reliably (hit twice converting jitterbug this
    project) -- if the session is still up after the wait, falls back to
    killing the matching processes directly, same as the manual fallback
    used during that conversion.
    """

    if not realm_running(server.data_dir, runner=runner):
        return

    runner(["screen", "-S", server.data_dir, "-p", "0", "-X", "stuff", "stop\r"])

    elapsed = 0.0
    while elapsed < wait_seconds:
        sleep(poll_interval)
        elapsed += poll_interval
        if not realm_running(server.data_dir, runner=runner):
            return

    _kill_matching_processes(server.data_dir, runner=runner)


def verify_pin(pin_path: Path, candidate: str) -> bool:
    """Check a candidate PIN against the secret file, in constant time."""

    if not pin_path.exists():
        return False

    expected = pin_path.read_text(encoding="utf-8").strip()

    return hmac.compare_digest(expected, candidate.strip())
