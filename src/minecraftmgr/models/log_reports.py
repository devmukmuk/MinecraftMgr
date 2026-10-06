"""Data models for reports built from realm server logs (gravestones, player activity)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

Coord = tuple[int, int, int]


@dataclass(frozen=True)
class FoundGrave:
    """A 'has found ... grave' event from a server log."""

    file: str
    line_number: int
    event_number: int
    time: str
    player: str
    coord: Coord
    line: str


@dataclass
class PlacedGrave:
    """A 'Placed <player>'s Gravestone' event from a server log."""

    file: str
    line_number: int
    event_number: int
    time: str
    player: str
    coord: Coord
    dimension: str
    line: str
    found_entries: list[FoundGrave] = field(default_factory=list)


@dataclass
class GravestoneScanResult:
    """Placed graves split into found and still-missing."""

    log_folder: Path
    placed: list[PlacedGrave] = field(default_factory=list)
    found: list[PlacedGrave] = field(default_factory=list)
    missing: list[PlacedGrave] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class UserActivity:
    """First and latest day a player joined or left a realm."""

    player: str
    first_seen: date
    latest_seen: date
    days_seen: set[date] = field(default_factory=set)


@dataclass
class RealmUserReport:
    """Player activity for one realm, read from its logs folder."""

    server_id: str
    name: str
    status: str
    log_folder: Path
    users: dict[str, UserActivity] = field(default_factory=dict)
    ops: set[str] = field(default_factory=set)  # lowercased names from ops.json
    op_names: list[str] = field(default_factory=list)  # names from ops.json as written
    whitelist: list[str] = field(default_factory=list)  # names from whitelist.json
    warnings: list[str] = field(default_factory=list)
