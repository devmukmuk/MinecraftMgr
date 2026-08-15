"""Tests for sha256_file."""

from __future__ import annotations

import hashlib
from pathlib import Path

from minecraftmgr.utils.hashing import sha256_file


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    """sha256_file agrees with hashing the bytes directly."""

    path = tmp_path / "sample.bin"
    content = b"minecraftmgr" * 1000
    path.write_bytes(content)

    assert sha256_file(path) == hashlib.sha256(content).hexdigest()
