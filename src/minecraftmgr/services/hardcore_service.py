"""Summarize, archive and reset a hardcore realm's run.

A run lasts from a fresh world until the last player dies. The summary is
built from two sources in the realm folder:

- ``<level-name>/players/stats/<uuid>.json`` (26.x; ``<level-name>/stats/``
  before that), with names from ``usercache.json``: exact play time, and a
  death count that catches a death the logs missed.
- ``logs/``: when each player first joined, and the timestamped death
  message that gives the order of deaths. Death messages have no fixed
  shape, so a line counts as a death when it is a known player's name
  followed by one of the vanilla death-message openings.

Archive & Reset (only once everyone has died) stops the realm, tars the
world folders and logs to ``<backups_root>/hardcore/<server_id>/``, appends
the summary to ``hardcore_runs.json`` in the realm folder, deletes the world
and logs, and sets ``level-seed`` for the next world (blank = random). The
jar, configs, whitelist, ops and plugins stay, so the next start makes a
new world. Clearing ``logs/`` is what keeps the next run's summary its own.
"""

from __future__ import annotations

import json
import re
import shutil
import tarfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from minecraftmgr.config.settings import Settings
from minecraftmgr.models.hardcore_run import HardcorePlayer, HardcoreRun
from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.backup_service import resolve_server_data_dir
from minecraftmgr.services.gravestone_service import iter_log_files, read_log_file
from minecraftmgr.services.server_properties_service import read_properties, set_properties
from minecraftmgr.services.trigger_service import CommandRunner, _default_runner, stop_realm
from minecraftmgr.services.user_report_service import log_date
from minecraftmgr.utils.hashing import sha256_file

RUNS_FILE_NAME = "hardcore_runs.json"
MAX_SEED_LENGTH = 64

# "[12:34:56 INFO]: msg" (Paper) or "[12:34:56] [Server thread/INFO]: msg" (vanilla). Since 26.3,
# join/leave/death lines read "...: System chat: <player> joined the game"; the prefix is dropped.
LOG_LINE_RE = re.compile(
    r"^\[(?P<time>\d\d:\d\d:\d\d)[^\]]*\](?: \[[^\]]*\])?: (?:System chat: )?(?P<msg>.*?)\s*$",
    re.MULTILINE,
)
JOINED_RE = re.compile(r"^(?P<player>[A-Za-z0-9_]+) joined the game$")

# How vanilla death messages continue after the player's name.
DEATH_OPENINGS = (
    "was ",
    "died",
    "drowned",
    "blew up",
    "burned to death",
    "discovered the floor was lava",
    "didn't want to live",
    "experienced kinetic energy",
    "fell ",
    "froze to death",
    "hit the ground too hard",
    "left the confines of this world",
    "starved to death",
    "suffocated in a wall",
    "tried to swim in lava",
    "walked into ",
    "went off with a bang",
    "went up in flames",
    "withered away",
)
NOT_DEATHS = ("was kicked",)


class HardcoreError(Exception):
    """Raised when a hardcore realm can't be reset."""


def _level_name(realm_dir: Path) -> str:
    properties = realm_dir / "server.properties"
    if not properties.is_file():
        return "world"
    return read_properties(properties).get("level-name") or "world"


def world_dirs(realm_dir: Path) -> list[Path]:
    """Return the world folders a reset clears.

    26.x keeps every dimension (and player data) inside <level>/; older Paper versions
    split the nether and end into <level>_nether and <level>_the_end.
    """

    level = _level_name(realm_dir)
    return [realm_dir / level, realm_dir / f"{level}_nether", realm_dir / f"{level}_the_end"]


def _read_stats(realm_dir: Path) -> dict[str, tuple[int | None, int]]:
    """Return {player: (play_seconds, deaths)} from the world's stats files."""

    names: dict[str, str] = {}
    try:
        for item in json.loads((realm_dir / "usercache.json").read_text(encoding="utf-8-sig")):
            names[str(item["uuid"])] = str(item["name"])
    except (OSError, ValueError, TypeError, KeyError):
        pass

    stats: dict[str, tuple[int | None, int]] = {}
    level_dir = realm_dir / _level_name(realm_dir)
    # 26.x keeps player data under <level>/players/; older versions under <level>/stats.
    paths = sorted((level_dir / "players" / "stats").glob("*.json")) or sorted(
        (level_dir / "stats").glob("*.json")
    )
    for path in paths:
        name = names.get(path.stem)
        if name is None:
            continue
        try:
            custom = json.loads(path.read_text(encoding="utf-8"))["stats"].get("minecraft:custom", {})
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue
        ticks = custom.get("minecraft:play_time", custom.get("minecraft:play_one_minute"))
        stats[name] = (None if ticks is None else int(ticks) // 20, int(custom.get("minecraft:deaths", 0)))
    return stats


def _death_message(msg: str, players: dict[str, str]) -> tuple[str, str] | None:
    """Return (player, message) if a log message is a known player's death, else None."""

    name, _, rest = msg.partition(" ")
    player = players.get(name.lower())
    if player is None or rest.startswith(NOT_DEATHS) or not rest.startswith(DEATH_OPENINGS):
        return None
    return player, msg


def _log_events(log_folder: Path) -> list[tuple[datetime, str]]:
    """Return (timestamp, message) for every log line, oldest first.

    The day comes from the log's name (or latest.log's modified time); a time
    earlier than the line before it means the log ran past midnight.
    """

    events: list[tuple[datetime, str]] = []
    for path in iter_log_files(log_folder) if log_folder.is_dir() else []:
        try:
            text = read_log_file(path)
        except (OSError, EOFError):
            continue
        day: date = log_date(path)
        previous = None
        for match in LOG_LINE_RE.finditer(text):
            clock = datetime.strptime(match.group("time"), "%H:%M:%S").time()
            if previous is not None and clock < previous:
                day += timedelta(days=1)
            previous = clock
            events.append((datetime.combine(day, clock), match.group("msg")))
    return events


def build_run_summary(realm_dir: Path) -> HardcoreRun:
    """Summarize the current run from the realm's logs and world stats."""

    events = _log_events(realm_dir / "logs")
    stats = _read_stats(realm_dir)

    players: dict[str, HardcorePlayer] = {}
    started_at: datetime | None = None
    for when, msg in events:
        joined = JOINED_RE.match(msg)
        if joined:
            name = joined.group("player")
            players.setdefault(name.lower(), HardcorePlayer(name))
            started_at = started_at or when
    for name in stats:
        players.setdefault(name.lower(), HardcorePlayer(name))

    by_name = {key: player.player for key, player in players.items()}
    deaths: list[tuple[datetime, str]] = []
    for when, msg in events:
        death = _death_message(msg, by_name)
        if death is None:
            continue
        player = players[death[0].lower()]
        if player.died_at is None:
            player.died_at = when.isoformat()
            player.death_message = death[1]
            player.dead = True
            deaths.append((when, player.player))

    for player in players.values():
        play_seconds, death_count = stats.get(player.player, (None, 0))
        player.play_seconds = play_seconds
        player.dead = player.dead or death_count > 0

    for order, (_, name) in enumerate(sorted(deaths), start=1):
        players[name.lower()].death_order = order

    # Died, in order; dead with no death message in the logs; then the living, A-Z.
    ordered = sorted(
        players.values(),
        key=lambda p: (p.death_order is None, p.death_order or 0, not p.dead, p.player.lower()),
    )
    run = HardcoreRun(players=ordered, started_at=started_at.isoformat() if started_at else None)
    if run.everyone_dead and deaths:
        run.ended_at = max(deaths)[0].isoformat()
        run.last_alive = max(deaths)[1]
    return run


def load_runs(realm_dir: Path) -> list[dict]:
    """Return the archived runs for a realm, oldest first."""

    path = realm_dir / RUNS_FILE_NAME
    if not path.is_file():
        return []
    try:
        runs = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return runs if isinstance(runs, list) else []


def hardcore_report(settings: Settings, servers: list[ServerEntry]) -> dict[str, dict]:
    """Return {server_id: {"current": run, "runs": [past runs]}} for each hardcore realm."""

    report: dict[str, dict] = {}
    for server in servers:
        if server.mode != "hardcore":
            continue
        realm_dir = resolve_server_data_dir(settings, server)
        report[server.server_id] = {
            "current": build_run_summary(realm_dir).to_dict(),
            "runs": load_runs(realm_dir),
        }
    return report


def clean_seed(seed: str) -> str:
    """Validate a requested seed: one line, at most MAX_SEED_LENGTH characters. Blank = random."""

    seed = seed.strip()
    if len(seed) > MAX_SEED_LENGTH or any(ch in seed for ch in "\r\n\\"):
        raise HardcoreError(f"Seed must be one line of at most {MAX_SEED_LENGTH} characters, no backslashes")
    return seed


def _archive(realm_dir: Path, archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in [*world_dirs(realm_dir), realm_dir / "logs", realm_dir / "server.properties"]:
            if path.exists():
                archive.add(path, arcname=path.name)
    # Read the whole archive back before anything is deleted.
    with tarfile.open(archive_path, "r:gz") as archive:
        archive.getmembers()
    digest = sha256_file(archive_path)
    archive_path.with_name(archive_path.name + ".sha256").write_text(
        f"{digest}  {archive_path.name}\n", encoding="utf-8"
    )


def archive_and_reset(
    settings: Settings,
    server: ServerEntry,
    seed: str = "",
    *,
    runner: CommandRunner = _default_runner,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> HardcoreRun:
    """Archive a finished hardcore run and clear the world for a new one; returns the run's summary.

    Refuses unless the realm is hardcore and every player in the run has died.
    """

    if server.mode != "hardcore":
        raise HardcoreError(f"'{server.server_id}' is not a hardcore realm")

    seed = clean_seed(seed)
    realm_dir = resolve_server_data_dir(settings, server)
    if not (realm_dir / "server.properties").is_file():
        raise HardcoreError(f"{realm_dir} is not a realm folder (no server.properties)")

    current = build_run_summary(realm_dir)
    if not current.players:
        raise HardcoreError("No one has played this run yet")
    if current.alive:
        raise HardcoreError(f"Still alive: {', '.join(current.alive)}")

    # Stopping saves the latest stats, so summarize again afterwards.
    stop_realm(server, settings.data_root, runner=runner)
    run = build_run_summary(realm_dir)

    runs = load_runs(realm_dir)
    reset_at = now()
    run.run = len(runs) + 1
    run.seed = read_properties(realm_dir / "server.properties").get("level-seed") or "random"
    run.reset_at = reset_at.isoformat()
    archive_path = (
        settings.backups_root
        / "hardcore"
        / server.server_id
        / f"{server.server_id}-run{run.run}-{reset_at.strftime('%Y%m%dT%H%M%SZ')}.tar.gz"
    )
    run.archive = archive_path.name

    _archive(realm_dir, archive_path)
    (realm_dir / RUNS_FILE_NAME).write_text(
        json.dumps([*runs, run.to_dict()], indent=2) + "\n", encoding="utf-8"
    )

    for path in [*world_dirs(realm_dir), realm_dir / "logs"]:
        if path.exists():
            shutil.rmtree(path)
    set_properties(realm_dir, {"level-seed": seed})

    return run
