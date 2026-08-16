"""Tests for the _jarcache resolver -- cache-only by default, no network,
and verifies a cached jar is actually Paper before trusting it."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from minecraftmgr.services.jar_cache_service import (
    JarCacheMiss,
    JarCacheWrongEngine,
    ensure_jar_cached,
    jar_cache_filename,
    resolve_cached_jar,
)


def _make_jar(path: Path, main_class: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/MANIFEST.MF", f"Manifest-Version: 1.0\nMain-Class: {main_class}\n")


def test_jar_cache_filename_replaces_dots_with_underscores() -> None:
    """Version dots become underscores, matching the real _jarcache naming convention."""

    assert jar_cache_filename("26.1.2") == "server_26_1_2.jar"


def test_resolve_cached_jar_finds_existing_file(tmp_path: Path) -> None:
    """A cached jar is found when it exists."""

    cache_dir = tmp_path / "_jarcache"
    cache_dir.mkdir()
    _make_jar(cache_dir / "server_1_21_10.jar", "io.papermc.paperclip.Paperclip")

    result = resolve_cached_jar(tmp_path, "1.21.10")

    assert result == cache_dir / "server_1_21_10.jar"


def test_resolve_cached_jar_returns_none_when_missing(tmp_path: Path) -> None:
    """A missing version resolves to None, not an error."""

    assert resolve_cached_jar(tmp_path, "1.21.10") is None


def test_ensure_jar_cached_returns_existing_paper_jar(tmp_path: Path) -> None:
    """An already-cached, positively-Paper jar is returned directly, no fetcher needed."""

    cache_dir = tmp_path / "_jarcache"
    cache_dir.mkdir()
    _make_jar(cache_dir / "server_26_1_2.jar", "io.papermc.paperclip.Paperclip")

    result = ensure_jar_cached(tmp_path, "26.1.2")

    assert result == cache_dir / "server_26_1_2.jar"


def test_ensure_jar_cached_raises_jar_cache_miss_without_fetcher(tmp_path: Path) -> None:
    """A missing version with no fetcher raises JarCacheMiss, never touches the network."""

    with pytest.raises(JarCacheMiss, match="1.21.10"):
        ensure_jar_cached(tmp_path, "1.21.10")


def test_ensure_jar_cached_uses_fetcher_when_given(tmp_path: Path) -> None:
    """A missing version with a fetcher calls it and returns the fetched Paper jar's path."""

    calls: list[tuple[str, Path]] = []

    def fake_fetcher(version: str, dest: Path) -> None:
        calls.append((version, dest))
        _make_jar(dest, "io.papermc.paperclip.Paperclip")

    result = ensure_jar_cached(tmp_path, "1.21.10", fetcher=fake_fetcher)

    assert result.exists()
    assert calls == [("1.21.10", tmp_path / "_jarcache" / "server_1_21_10.jar")]


def test_ensure_jar_cached_rejects_a_vanilla_jar_under_the_right_filename(tmp_path: Path) -> None:
    """A cached jar matching the naming convention but not actually Paper is refused.

    Confirmed live on oscar: every jar in _jarcache turned out to be vanilla,
    despite matching the server_<version>.jar convention -- a filename match
    is not proof of what's actually inside.
    """

    cache_dir = tmp_path / "_jarcache"
    cache_dir.mkdir()
    _make_jar(cache_dir / "server_26_1_2.jar", "net.minecraft.bundler.Main")

    with pytest.raises(JarCacheWrongEngine, match="vanilla"):
        ensure_jar_cached(tmp_path, "26.1.2")


def test_ensure_jar_cached_skips_validation_when_require_paper_false(tmp_path: Path) -> None:
    """require_paper=False is an explicit opt-out, for callers that genuinely don't need Paper."""

    cache_dir = tmp_path / "_jarcache"
    cache_dir.mkdir()
    _make_jar(cache_dir / "server_26_1_2.jar", "net.minecraft.bundler.Main")

    result = ensure_jar_cached(tmp_path, "26.1.2", require_paper=False)

    assert result == cache_dir / "server_26_1_2.jar"
