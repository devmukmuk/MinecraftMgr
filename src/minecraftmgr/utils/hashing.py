"""File hashing helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Return the hex sha256 digest of a file, reading it in chunks."""

    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)

    return digest.hexdigest()
