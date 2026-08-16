"""Tests for the _jarcache resolver -- cache-only by default, no network."""

from __future__ import annotations

from pathlib import Path

import pytest

from minecraftmgr.services.jar_cache_service import (
    JarCacheMiss,
    ensure_jar_cached,
    jar_cache_filename,
    resolve_cached_jar,
)


def test_jar_cache_filename_replaces_dots_with_underscores() -> None:
    """Version dots become underscores, matching the real _jarcache naming convention."""

    assert jar_cache_filename("26.1.2") == "server_26_1_2.jar"


def test_resolve_cached_jar_finds_existing_file(tmp_path: Path) -> None:
    """A cached jar is found when it exists."""

    cache_dir = tmp_path / "_jarcache"
    cache_dir.mkdir()
    (cache_dir / "server_1_21_10.jar").write_bytes(b"fake jar")

    result = resolve_cached_jar(tmp_path, "1.21.10")

    assert result == cache_dir / "server_1_21_10.jar"


def test_resolve_cached_jar_returns_none_when_missing(tmp_path: Path) -> None:
    """A missing version resolves to None, not an error."""

    assert resolve_cached_jar(tmp_path, "1.21.10") is None


def test_ensure_jar_cached_returns_existing_without_fetcher(tmp_path: Path) -> None:
    """An already-cached jar is returned directly, no fetcher needed."""

    cache_dir = tmp_path / "_jarcache"
    cache_dir.mkdir()
    (cache_dir / "server_26_1_2.jar").write_bytes(b"fake jar")

    result = ensure_jar_cached(tmp_path, "26.1.2")

    assert result == cache_dir / "server_26_1_2.jar"


def test_ensure_jar_cached_raises_jar_cache_miss_without_fetcher(tmp_path: Path) -> None:
    """A missing version with no fetcher raises JarCacheMiss, never touches the network."""

    with pytest.raises(JarCacheMiss, match="1.21.10"):
        ensure_jar_cached(tmp_path, "1.21.10")


def test_ensure_jar_cached_uses_fetcher_when_given(tmp_path: Path) -> None:
    """A missing version with a fetcher calls it and returns the fetched path."""

    calls: list[tuple[str, Path]] = []

    def fake_fetcher(version: str, dest: Path) -> None:
        calls.append((version, dest))
        dest.write_bytes(b"downloaded jar")

    result = ensure_jar_cached(tmp_path, "1.21.10", fetcher=fake_fetcher)

    assert result.exists()
    assert result.read_bytes() == b"downloaded jar"
    assert calls == [("1.21.10", tmp_path / "_jarcache" / "server_1_21_10.jar")]
