"""Data model for the outcome of a single realm backup."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BackupResult:
    """Outcome of backing up one realm's data directory."""

    server_id: str
    archive_path: Path
    sha256_path: Path
    size_bytes: int
    sha256: str
    created_at: str
