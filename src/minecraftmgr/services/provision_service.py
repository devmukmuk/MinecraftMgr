"""First-boot orchestration for newly scaffolded or activated realms.

Chains trigger_service's start/stop primitives with a wait-for-ready poll,
to generate a realm's config/paper-global.yml (which Paper only writes on
first boot) so its Velocity trust block can then be patched in.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

import yaml

from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services import trigger_service
from minecraftmgr.services.trigger_service import CommandRunner

_DONE_MARKER = "]: Done ("


class ReadinessTimeout(Exception):
    """Raised when a realm doesn't show its ready marker within the timeout."""


class RealmCrashedBeforeReady(Exception):
    """Raised when the realm process exits before its ready marker appears."""


def _default_runner(
    args: list[str], cwd: Optional[Path] = None
) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


def _default_read_log_tail(log_path: Path) -> str:
    if not log_path.exists():
        return ""
    return log_path.read_text(encoding="utf-8", errors="replace")


def wait_for_ready(
    log_path: Path,
    *,
    started_at: float,
    still_running: Callable[[], bool],
    timeout_seconds: float = 180,
    poll_interval: float = 2,
    done_marker: str = _DONE_MARKER,
    read_log_tail: Callable[[Path], str] = _default_read_log_tail,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    """Poll log_path for done_marker, only trusting content written since started_at.

    `started_at` is a wall-clock (time.time()) timestamp, compared against
    the log file's own mtime -- this guards the exact stale-latest.log
    false positive hit converting jitterbug, where a crashed duplicate
    start's tiny new log hid the real successful boot behind an
    already-rotated archive of the previous run. `monotonic` is used only
    for measuring the timeout, a deliberately separate clock domain.
    """

    deadline = monotonic() + timeout_seconds

    while monotonic() < deadline:
        if log_path.exists() and log_path.stat().st_mtime >= started_at:
            if done_marker in read_log_tail(log_path):
                return

        if not still_running():
            raise RealmCrashedBeforeReady(
                f"Process exited before '{done_marker.strip()}' appeared in {log_path}"
            )

        sleep(poll_interval)

    raise ReadinessTimeout(
        f"Realm did not become ready within {timeout_seconds}s (log: {log_path})"
    )


def first_boot_cycle(
    server: ServerEntry,
    data_root: Path,
    *,
    runner: CommandRunner = _default_runner,
    sleep: Callable[[float], None] = time.sleep,
    timeout_seconds: float = 180,
) -> Path:
    """Run a realm through start -> wait-for-ready -> stop, to generate its
    first-boot-only config/paper-global.yml.

    Does NOT auto-kill on ReadinessTimeout or RealmCrashedBeforeReady --
    both re-raise and leave the process as it is, for a human to inspect
    (`screen -r`) rather than risking a corrupt kill mid-boot.
    """

    started_at = time.time()

    trigger_service.start_realm(server, data_root, runner=runner)

    log_path = data_root / server.data_dir / "logs" / "latest.log"

    def _still_running() -> bool:
        return trigger_service.realm_running(server.data_dir, runner=runner)

    wait_for_ready(
        log_path,
        started_at=started_at,
        still_running=_still_running,
        timeout_seconds=timeout_seconds,
        sleep=sleep,
    )

    trigger_service.stop_realm(server, data_root, runner=runner, sleep=sleep)

    return data_root / server.data_dir / "config" / "paper-global.yml"


def patch_velocity_trust(paper_global_path: Path, secret: str, *, online_mode: bool = True) -> None:
    """Patch config/paper-global.yml's Velocity trust block.

    Raises FileNotFoundError if the file doesn't exist yet (needs a first
    boot first, see first_boot_cycle). Re-dumps the whole file via PyYAML
    rather than a targeted text patch -- loses comments, same tradeoff
    already accepted converting gravestone/jitterbug by hand this session.
    """

    if not paper_global_path.exists():
        raise FileNotFoundError(
            f"{paper_global_path} doesn't exist yet -- the realm needs a first boot "
            "(see first_boot_cycle) before its Velocity trust config can be patched."
        )

    data = yaml.safe_load(paper_global_path.read_text(encoding="utf-8")) or {}

    proxies = data.setdefault("proxies", {})
    velocity = proxies.setdefault("velocity", {})
    velocity["enabled"] = True
    velocity["online-mode"] = online_mode
    velocity["secret"] = secret

    paper_global_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
