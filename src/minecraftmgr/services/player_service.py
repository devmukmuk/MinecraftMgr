"""Determine which real Minecraft usernames are currently online for a realm.

RCON is disabled on every realm (see capacity_service) and screen has no
programmatic way to capture an in-game `list` response, so the server's own
log is the only source of real usernames. Only `logs/latest.log` is read --
it always starts fresh at server boot, so a still-connected player's join
line is guaranteed to be in it even after log rotation. Join/leave line shape
matches screenshot_matcher_service's own parsing of the same logs.
"""

from __future__ import annotations

import re
from pathlib import Path

_JOIN_RE = re.compile(r"\[\d{2}:\d{2}:\d{2}\].*?: (\S+) joined the game")
_LEAVE_RE = re.compile(r"\[\d{2}:\d{2}:\d{2}\].*?: (\S+) left the game")


def active_players(logs_dir: Path) -> list[str]:
    """Return usernames currently online, in join order, for a realm's live log.

    Replays join/leave events from logs/latest.log in file order. A leave
    with no matching prior join is ignored rather than erroring, since a
    truncated or rotated log could plausibly start mid-session.
    """

    latest_log = logs_dir / "latest.log"

    if not latest_log.is_file():
        return []

    online: list[str] = []

    with latest_log.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            join_match = _JOIN_RE.search(line)
            if join_match:
                name = join_match.group(1)
                if name not in online:
                    online.append(name)
                continue

            leave_match = _LEAVE_RE.search(line)
            if leave_match:
                name = leave_match.group(1)
                if name in online:
                    online.remove(name)

    return online
