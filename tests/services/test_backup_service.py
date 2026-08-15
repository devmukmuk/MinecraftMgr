"""Tests for the realm backup service."""

from __future__ import annotations

import tarfile

import pytest

from minecraftmgr.config.settings import Settings
from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.backup_service import BackupError, backup_server, backup_servers
from minecraftmgr.utils.hashing import sha256_file


def _entry(server_id: str) -> ServerEntry:
    return ServerEntry(
        server_id=server_id,
        name=server_id.title(),
        status="active",
        port=25565,
        minecraft_version="1.21.10",
        server_type="paper",
        jar_source="",
        data_dir=server_id,
        created="2026-08-15T21:00:00+00:00",
        notes="",
    )


def test_backup_server_creates_verified_archive(settings: Settings) -> None:
    """backup_server tars the data dir and records a matching sha256."""

    entry = _entry("gatorland")
    data_dir = settings.data_root / entry.data_dir
    data_dir.mkdir()
    (data_dir / "world.dat").write_text("world data", encoding="utf-8")

    result = backup_server(settings, entry)

    assert result.archive_path.exists()
    assert result.sha256_path.exists()
    assert sha256_file(result.archive_path) == result.sha256
    assert result.size_bytes == result.archive_path.stat().st_size

    with tarfile.open(result.archive_path) as archive:
        names = archive.getnames()

    assert "gatorland/world.dat" in names


def test_backup_server_missing_data_dir_raises(settings: Settings) -> None:
    """A realm whose data directory doesn't exist can't be backed up."""

    with pytest.raises(BackupError):
        backup_server(settings, _entry("missing"))


def test_backup_servers_collects_failures_without_aborting(settings: Settings) -> None:
    """One realm failing to back up doesn't stop the others in the batch."""

    ok_entry = _entry("gatorland")
    (settings.data_root / ok_entry.data_dir).mkdir()

    results, failures = backup_servers(settings, [ok_entry, _entry("missing")])

    assert [result.server_id for result in results] == ["gatorland"]
    assert [server_id for server_id, _ in failures] == ["missing"]
