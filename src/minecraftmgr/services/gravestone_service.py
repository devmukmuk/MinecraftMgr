"""Scan realm server logs for gravestone placed/found events (Gravestones mod).

Ported from MineOps (2026-10-05). The Gravestones mod logged
``Placed <player>'s Gravestone at (x, y, z) in <dimension>`` on death and
``<player> has found their grave at (x, y, z)`` on pickup; a placed grave
with no later found event at the same spot is still out there. Paper writes
the same ``[HH:MM:SS] [Server thread/INFO]:`` shape to its log files, so the
patterns work for both.
"""

from __future__ import annotations

import gzip
import re
from collections import defaultdict
from pathlib import Path

from minecraftmgr.models.log_reports import Coord, FoundGrave, GravestoneScanResult, PlacedGrave

PLACED_RE = re.compile(
    r"\[(?P<time>\d\d:\d\d:\d\d)\].*INFO\]: Placed (?P<player>.+?)'s Gravestone at "
    r"\((?P<x>-?\d+),\s*(?P<y>-?\d+),\s*(?P<z>-?\d+)\) in (?P<dim>[\w:]+)"
)

FOUND_RE = re.compile(
    r"\[(?P<time>\d\d:\d\d:\d\d)\].*INFO\]: (?P<player>\S+) has found .*grave at "
    r"\((?P<x>-?\d+),\s*(?P<y>-?\d+),\s*(?P<z>-?\d+)\)"
)


def iter_log_files(log_folder: Path) -> list[Path]:
    """Return a logs folder's files oldest first (dated .log.gz names sort, latest.log last)."""

    files = sorted(log_folder.glob("*.log.gz")) + sorted(
        path
        for pattern in ("*.log", "*.txt")
        for path in log_folder.glob(pattern)
        if path.name != "latest.log"
    )
    latest = log_folder / "latest.log"
    if latest.is_file():
        files.append(latest)
    return files


def read_log_file(path: Path) -> str:
    """Read a plain or gzipped log file."""

    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    return path.read_text(encoding="utf-8", errors="replace")


def _coord(match: re.Match[str]) -> Coord:
    return (int(match.group("x")), int(match.group("y")), int(match.group("z")))


def _player_matches(log_player: str, requested: str | None) -> bool:
    return requested is None or log_player.lower() == requested.lower()


def scan_gravestones(log_folder: Path, player: str | None = None) -> GravestoneScanResult:
    """Scan a logs folder and classify each placed grave as found or missing."""

    result = GravestoneScanResult(log_folder=log_folder)
    found_by_key: dict[tuple[str, Coord], list[FoundGrave]] = defaultdict(list)

    if not log_folder.is_dir():
        result.warnings.append(f"Log folder does not exist: {log_folder}")
        return result

    event_number = 0
    for path in iter_log_files(log_folder):
        try:
            text = read_log_file(path)
        except (OSError, EOFError) as exc:
            result.warnings.append(f"Could not read {path.name}: {exc}")
            continue

        for line_number, line in enumerate(text.splitlines(), start=1):
            event_number += 1

            placed = PLACED_RE.search(line)
            if placed and _player_matches(placed.group("player"), player):
                result.placed.append(
                    PlacedGrave(
                        file=path.name,
                        line_number=line_number,
                        event_number=event_number,
                        time=placed.group("time"),
                        player=placed.group("player"),
                        coord=_coord(placed),
                        dimension=placed.group("dim"),
                        line=line,
                    )
                )

            found = FOUND_RE.search(line)
            if found and _player_matches(found.group("player"), player):
                entry = FoundGrave(
                    file=path.name,
                    line_number=line_number,
                    event_number=event_number,
                    time=found.group("time"),
                    player=found.group("player"),
                    coord=_coord(found),
                    line=line,
                )
                found_by_key[(entry.player.lower(), entry.coord)].append(entry)

    # A grave counts as found only by a found event *after* it was placed.
    for grave in result.placed:
        later = sorted(
            (
                entry
                for entry in found_by_key.get((grave.player.lower(), grave.coord), [])
                if entry.event_number > grave.event_number
            ),
            key=lambda entry: entry.event_number,
        )
        if later:
            grave.found_entries = [later[0]]
            result.found.append(grave)
        else:
            result.missing.append(grave)

    return result
