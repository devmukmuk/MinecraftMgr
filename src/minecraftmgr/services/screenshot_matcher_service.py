"""Screenshot matcher: correlate screenshot timestamps with realm join/leave sessions.

Screenshots are always a client-side capture (Minecraft's F2 key) — nothing on
oscar records which realm a shot was taken on. This module rebuilds that link
after the fact by parsing each realm's own server logs for a target
username's `joined the game` / `left the game` lines, turning them into
session windows, and checking which window (if any) contains a screenshot's
filename timestamp.
"""

from __future__ import annotations

import gzip
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from minecraftmgr.models.screenshot_match import ScreenshotMatch

_FILENAME_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_SCREENSHOT_TIMESTAMP_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})_(\d{2})\.(\d{2})\.(\d{2})"
)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
UNSORTED_DIR_NAME = "_unsorted"

DEFAULT_SLACK = timedelta(seconds=5)


@dataclass(frozen=True)
class RealmSession:
    """One join-to-leave window for a username on a realm. end=None means still open."""

    start: datetime
    end: datetime | None


def parse_screenshot_timestamp(filename: str) -> datetime | None:
    """Parse Minecraft's own screenshot filename format (`YYYY-MM-DD_HH.MM.SS...`)."""

    match = _SCREENSHOT_TIMESTAMP_RE.match(filename)
    if not match:
        return None

    year, month, day, hour, minute, second = (int(group) for group in match.groups())

    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def _open_log(path: Path):
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="ignore")
    return path.open("r", encoding="utf-8", errors="ignore")


def _file_date(path: Path) -> str:
    match = _FILENAME_DATE_RE.match(path.name)
    if match:
        return match.group(1)

    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def _parse_log_events(logs_dir: Path, username: str) -> list[tuple[datetime, str]]:
    if not logs_dir.is_dir():
        return []

    join_re = re.compile(rf"\[(\d{{2}}:\d{{2}}:\d{{2}})\].*?: {re.escape(username)} joined the game")
    leave_re = re.compile(rf"\[(\d{{2}}:\d{{2}}:\d{{2}})\].*?: {re.escape(username)} left the game")

    log_files = sorted(
        path
        for path in logs_dir.iterdir()
        if path.is_file() and (path.name.endswith(".log") or path.name.endswith(".log.gz"))
    )

    events: list[tuple[datetime, str]] = []

    for log_file in log_files:
        file_date = _file_date(log_file)

        with _open_log(log_file) as handle:
            for line in handle:
                join_match = join_re.search(line)
                if join_match:
                    events.append((_combine(file_date, join_match.group(1)), "join"))
                    continue

                leave_match = leave_re.search(line)
                if leave_match:
                    events.append((_combine(file_date, leave_match.group(1)), "leave"))

    return sorted(events, key=lambda event: event[0])


def _combine(date_str: str, time_str: str) -> datetime:
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")


def build_realm_sessions(logs_dir: Path, username: str) -> list[RealmSession]:
    """Parse a realm's logs into join-to-leave session windows for a username."""

    events = _parse_log_events(logs_dir, username)

    sessions: list[RealmSession] = []
    open_start: datetime | None = None

    for timestamp, kind in events:
        if kind == "join":
            if open_start is None:
                open_start = timestamp
        elif kind == "leave" and open_start is not None:
            sessions.append(RealmSession(open_start, timestamp))
            open_start = None

    if open_start is not None:
        sessions.append(RealmSession(open_start, None))

    return sessions


def _session_contains(session: RealmSession, taken_at: datetime, slack: timedelta) -> bool:
    if taken_at < session.start - slack:
        return False

    if session.end is not None and taken_at > session.end + slack:
        return False

    return True


def match_realm(
    taken_at: datetime,
    realm_sessions: dict[str, list[RealmSession]],
    slack: timedelta = DEFAULT_SLACK,
) -> str | None:
    """Return the realm id whose session window contains taken_at, or None."""

    for realm_id, sessions in realm_sessions.items():
        for session in sessions:
            if _session_contains(session, taken_at, slack):
                return realm_id

    return None


def organize_screenshots(
    inbox_dir: Path,
    output_root: Path,
    realm_logs: dict[str, tuple[Path, str]],
    username: str,
    *,
    slack: timedelta = DEFAULT_SLACK,
) -> list[ScreenshotMatch]:
    """Match every screenshot in inbox_dir to a realm and move it into an organized tree.

    realm_logs maps realm_id -> (logs_dir, minecraft_version). Unmatched files
    (unparseable filename, or no session window contains the timestamp) move
    to `_unsorted/` instead of being dropped.
    """

    realm_sessions = {
        realm_id: build_realm_sessions(logs_dir, username)
        for realm_id, (logs_dir, _version) in realm_logs.items()
    }

    matches: list[ScreenshotMatch] = []

    if not inbox_dir.is_dir():
        return matches

    for source in sorted(inbox_dir.iterdir()):
        if not source.is_file() or source.suffix.lower() not in IMAGE_SUFFIXES:
            continue

        taken_at = parse_screenshot_timestamp(source.name)
        realm_id = match_realm(taken_at, realm_sessions, slack) if taken_at is not None else None

        if realm_id is not None:
            version = realm_logs[realm_id][1]
            relative_path = f"{realm_id}/{version}/{source.name}"
        else:
            version = None
            relative_path = f"{UNSORTED_DIR_NAME}/{source.name}"

        destination = output_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))

        matches.append(
            ScreenshotMatch(
                filename=source.name,
                taken_at=taken_at,
                realm=realm_id,
                minecraft_version=version,
                relative_path=relative_path,
                matched=realm_id is not None,
            )
        )

    return matches


def write_manifest(matches: list[ScreenshotMatch], path: Path) -> Path:
    """Write the screenshot manifest, sorted by relative_path for stable diffs."""

    path.parent.mkdir(parents=True, exist_ok=True)

    ordered = sorted(matches, key=lambda match: match.relative_path)
    path.write_text(
        json.dumps([match.to_dict() for match in ordered], indent=2) + "\n",
        encoding="utf-8",
    )

    return path


def merge_manifest(
    existing: list[ScreenshotMatch], new: list[ScreenshotMatch]
) -> list[ScreenshotMatch]:
    """Merge freshly organized matches into a prior manifest, keyed by relative_path.

    organize_screenshots only ever sees whatever's currently in the inbox, so
    writing its result straight to disk would forget every screenshot from a
    prior run that isn't in the inbox this time. New entries win on a
    relative_path collision; everything else from the prior manifest carries
    forward untouched.
    """

    merged = {match.relative_path: match for match in existing}
    merged.update({match.relative_path: match for match in new})

    return list(merged.values())


def load_manifest(path: Path) -> list[ScreenshotMatch]:
    """Load a screenshot manifest, or an empty list if it doesn't exist yet."""

    if not path.exists():
        return []

    data = json.loads(path.read_text(encoding="utf-8"))

    return [ScreenshotMatch.from_dict(entry) for entry in data]
