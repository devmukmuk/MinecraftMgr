"""Realm status checks and the remote-start action used by the trigger daemon.

Kept free of any HTTP/network concerns so it can be unit tested without a
live `screen` install -- callers inject a `runner` in tests.
"""

from __future__ import annotations

import hmac
import re
import subprocess
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


def verify_pin(pin_path: Path, candidate: str) -> bool:
    """Check a candidate PIN against the secret file, in constant time."""

    if not pin_path.exists():
        return False

    expected = pin_path.read_text(encoding="utf-8").strip()

    return hmac.compare_digest(expected, candidate.strip())
