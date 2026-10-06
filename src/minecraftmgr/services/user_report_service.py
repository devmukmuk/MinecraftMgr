"""Build per-realm player activity (first/latest day seen) from server logs.

Ported from MineOps (2026-10-05). Reads every ``logs/*.log.gz`` plus
``latest.log`` for each registry realm and records the days each player
joined or left. Dated log names (``2026-05-01-1.log.gz``) give the day;
``latest.log`` uses its modified time.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from minecraftmgr.config.settings import Settings
from minecraftmgr.models.log_reports import RealmUserReport, UserActivity
from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.backup_service import resolve_server_data_dir
from minecraftmgr.services.gravestone_service import iter_log_files, read_log_file

LOG_DATE_RE = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})")
PLAYER_EVENT_RE = re.compile(r"\]: (?P<player>[A-Za-z0-9_]+) (?:joined|left) the game")


def log_date(path: Path) -> date:
    """Return the day a log file covers: from its name, else its modified time."""

    match = LOG_DATE_RE.search(path.name)
    if match:
        return date.fromisoformat(match.group("date"))
    return datetime.fromtimestamp(path.stat().st_mtime).date()


def _names(path: Path, warnings: list[str]) -> list[str]:
    """Return the player names in an ops.json/whitelist.json; warn if it exists but can't be read."""

    if not path.exists():
        return []
    try:
        return [str(item["name"]) for item in json.loads(path.read_text(encoding="utf-8-sig"))]
    except (OSError, ValueError, TypeError, KeyError) as exc:
        warnings.append(f"Could not read {path.name} ({type(exc).__name__}: {exc}); treated as empty")
        return []


def build_realm_report(log_folder: Path, entry: ServerEntry) -> RealmUserReport:
    """Build player activity for one realm from its logs folder, plus its ops and whitelist."""

    realm_dir = log_folder.parent
    report = RealmUserReport(
        server_id=entry.server_id,
        name=entry.name,
        status=entry.status.lower(),
        log_folder=log_folder,
    )
    op_names = _names(realm_dir / "ops.json", report.warnings)
    report.ops = {name.lower() for name in op_names}
    report.op_names = op_names
    report.whitelist = _names(realm_dir / "whitelist.json", report.warnings)

    if not log_folder.is_dir():
        report.warnings.append(f"Log folder does not exist: {log_folder}")
        return report

    for path in iter_log_files(log_folder):
        try:
            text = read_log_file(path)
        except (OSError, EOFError) as exc:
            report.warnings.append(f"Could not read {path.name}: {exc}")
            continue

        day = log_date(path)
        for match in PLAYER_EVENT_RE.finditer(text):
            player = match.group("player")
            user = report.users.get(player)
            if user is None:
                user = report.users[player] = UserActivity(player, first_seen=day, latest_seen=day)
            user.first_seen = min(user.first_seen, day)
            user.latest_seen = max(user.latest_seen, day)
            user.days_seen.add(day)

    return report


def build_user_report(settings: Settings, servers: list[ServerEntry]) -> list[RealmUserReport]:
    """Build player activity for each realm, reading <data_root>/<data_dir>/logs."""

    return [
        build_realm_report(resolve_server_data_dir(settings, entry) / "logs", entry)
        for entry in servers
    ]


def realm_rows(report: RealmUserReport) -> list[dict]:
    """Merge players seen in the logs with the whitelist and ops, flagging ops.

    Each row: player, first_seen/latest_seen (ISO date, or None if never played), days,
    op, whitelisted. Players who have played come first (newest first), then whitelisted
    players and ops who haven't played yet, A-Z (ops can join without being whitelisted).
    Names match case-insensitively.
    """

    whitelisted = {name.lower() for name in report.whitelist}
    rows = [
        {
            "player": user.player,
            "first_seen": user.first_seen.isoformat(),
            "latest_seen": user.latest_seen.isoformat(),
            "days": len(user.days_seen),
            "op": user.player.lower() in report.ops,
            "whitelisted": user.player.lower() in whitelisted,
        }
        for user in sorted(report.users.values(), key=lambda u: u.latest_seen, reverse=True)
    ]
    seen = {user.lower() for user in report.users}
    not_played: list[str] = []
    for name in [*report.whitelist, *report.op_names]:  # first spelling wins
        if name.lower() not in seen:
            seen.add(name.lower())
            not_played.append(name)
    rows += [
        {
            "player": name,
            "first_seen": None,
            "latest_seen": None,
            "days": 0,
            "op": name.lower() in report.ops,
            "whitelisted": name.lower() in whitelisted,
        }
        for name in sorted(not_played, key=str.lower)
    ]
    return rows


def players_by_realm(settings: Settings, servers: list[ServerEntry]) -> dict[str, list[dict]]:
    """Return {server_id: realm_rows(...)} for the realm page."""

    return {realm.server_id: realm_rows(realm) for realm in build_user_report(settings, servers)}
