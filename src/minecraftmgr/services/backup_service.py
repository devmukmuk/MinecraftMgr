"""Backup service: archive a realm's data directory with sha256 verification."""

from __future__ import annotations

import tarfile
from datetime import datetime, timezone
from pathlib import Path

from minecraftmgr.config.settings import Settings
from minecraftmgr.models.backup_result import BackupResult
from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.utils.hashing import sha256_file


class BackupError(Exception):
    """Raised when a realm cannot be backed up."""


def resolve_server_data_dir(settings: Settings, entry: ServerEntry) -> Path:
    """Return the on-disk data directory for a registry entry."""

    return settings.data_root / entry.data_dir


def backup_server(settings: Settings, entry: ServerEntry) -> BackupResult:
    """Archive one realm's data directory and record its sha256 checksum."""

    data_dir = resolve_server_data_dir(settings, entry)

    if not data_dir.is_dir():
        raise BackupError(f"Data directory not found for '{entry.server_id}': {data_dir}")

    settings.backups_root.mkdir(parents=True, exist_ok=True)

    created_at = datetime.now(timezone.utc)
    timestamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    archive_path = settings.backups_root / f"{entry.server_id}-{timestamp}.tar.gz"

    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(data_dir, arcname=entry.server_id)

    digest = sha256_file(archive_path)
    sha256_path = archive_path.with_name(archive_path.name + ".sha256")
    sha256_path.write_text(f"{digest}  {archive_path.name}\n", encoding="utf-8")

    return BackupResult(
        server_id=entry.server_id,
        archive_path=archive_path,
        sha256_path=sha256_path,
        size_bytes=archive_path.stat().st_size,
        sha256=digest,
        created_at=created_at.isoformat(),
    )


def backup_servers(
    settings: Settings, entries: list[ServerEntry]
) -> tuple[list[BackupResult], list[tuple[str, str]]]:
    """Back up multiple realms, collecting per-realm failures instead of aborting the batch."""

    results: list[BackupResult] = []
    failures: list[tuple[str, str]] = []

    for entry in entries:
        try:
            results.append(backup_server(settings, entry))
        except BackupError as exc:
            failures.append((entry.server_id, str(exc)))

    return results, failures
