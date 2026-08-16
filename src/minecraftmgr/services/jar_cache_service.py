"""Resolve a Minecraft version to a jar in the shared /opt/mc/_jarcache/.

Cache-only for now -- deliberately does not call PaperMC's Fill API to
download a missing jar. That API's response shape has only been exercised
manually via curl so far, never automated or checksum-verified, and
installing an unverified binary as a production server jar deserves that
treatment before it's automated. The `fetcher` injection point exists so
that can be added later without touching callers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

JarFetcher = Callable[[str, Path], None]

_JARCACHE_DIRNAME = "_jarcache"


class JarCacheError(Exception):
    """Raised for jar cache problems."""


class JarCacheMiss(JarCacheError):
    """Raised when a version isn't cached and no fetcher was given to fetch it."""


def jar_cache_filename(minecraft_version: str) -> str:
    """Return the _jarcache filename for a Minecraft version, e.g. '26.1.2' -> 'server_26_1_2.jar'."""

    return f"server_{minecraft_version.replace('.', '_')}.jar"


def resolve_cached_jar(data_root: Path, minecraft_version: str) -> Optional[Path]:
    """Return the cached jar path for a version, or None if it isn't cached."""

    candidate = data_root / _JARCACHE_DIRNAME / jar_cache_filename(minecraft_version)

    return candidate if candidate.exists() else None


def ensure_jar_cached(
    data_root: Path,
    minecraft_version: str,
    *,
    fetcher: Optional[JarFetcher] = None,
) -> Path:
    """Return the cached jar path for a version, fetching it first if a fetcher is given.

    With fetcher=None (the default), never touches the network -- raises
    JarCacheMiss if the version isn't already cached.
    """

    cached = resolve_cached_jar(data_root, minecraft_version)
    if cached is not None:
        return cached

    if fetcher is None:
        filename = jar_cache_filename(minecraft_version)
        raise JarCacheMiss(
            f"'{minecraft_version}' is not in _jarcache/ ({filename} not found). "
            "Download the right Paper build manually (fill.papermc.io) into "
            f"{data_root / _JARCACHE_DIRNAME}, then re-run."
        )

    dest = data_root / _JARCACHE_DIRNAME / jar_cache_filename(minecraft_version)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fetcher(minecraft_version, dest)

    return dest
