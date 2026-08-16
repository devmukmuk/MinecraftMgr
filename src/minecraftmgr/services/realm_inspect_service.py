"""Inspect a realm's data directory to positively identify its server engine.

Absence of a `mods/` directory is NOT sufficient evidence of Paper
compatibility -- `jitterbug` had no `mods/` dir and was still vanilla,
which is just as incompatible with Velocity's forwarding as Fabric/Forge.
Detection here is positive: it reads the server jar's `Main-Class` from
its manifest rather than guessing from folder shape.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from minecraftmgr.models.realm_inspection import RealmInspection

_MAIN_CLASS_MARKERS = (
    ("paperclip", "paper"),
    ("fabricmc", "fabric"),
    ("bootstraplauncher", "forge"),
    ("fml", "forge"),
    ("net.minecraft", "vanilla"),
)


class IncompatibleRealmError(Exception):
    """Raised when a realm isn't safely activatable behind Velocity."""


def _find_server_jar(realm_dir: Path) -> Path | None:
    """Return the most recently modified server_*.jar, or None if none exist."""

    candidates = sorted(
        realm_dir.glob("server_*.jar"), key=lambda path: path.stat().st_mtime, reverse=True
    )

    return candidates[0] if candidates else None


def read_jar_main_class(jar_path: Path) -> str | None:
    """Read the Main-Class attribute out of a jar's manifest, if readable.

    Public: reused by jar_cache_service to verify a cached jar is actually
    Paper before provision trusts it, not just this module's own realm
    folder inspection.
    """

    try:
        with zipfile.ZipFile(jar_path) as archive:
            manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace")
    except (KeyError, zipfile.BadZipFile, OSError):
        return None

    for line in manifest.splitlines():
        if line.startswith("Main-Class:"):
            return line.split(":", 1)[1].strip()

    return None


def classify_main_class(main_class: str | None) -> str:
    """Map a jar's Main-Class to a best-effort server_type, or 'unknown'."""

    if main_class is None:
        return "unknown"

    lowered = main_class.lower()

    for marker, server_type in _MAIN_CLASS_MARKERS:
        if marker in lowered:
            return server_type

    return "unknown"


def classify_jar(jar_path: Path) -> str:
    """Classify a jar file's engine type directly from its manifest."""

    return classify_main_class(read_jar_main_class(jar_path))


def _read_online_mode(properties_path: Path) -> bool:
    """Read online-mode from server.properties, defaulting to False if absent/unset."""

    if not properties_path.exists():
        return False

    for line in properties_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("online-mode="):
            return line.split("=", 1)[1].strip().lower() == "true"

    return False


def _read_server_port(properties_path: Path) -> int | None:
    """Read server-port from server.properties, or None if absent/unset/unparseable."""

    if not properties_path.exists():
        return None

    for line in properties_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("server-port="):
            value = line.split("=", 1)[1].strip()
            return int(value) if value.isdigit() else None

    return None


def inspect_realm_dir(realm_dir: Path) -> RealmInspection:
    """Inspect a realm's data directory and positively identify its server engine."""

    notes: list[str] = []

    has_mods_dir = (realm_dir / "mods").is_dir()

    jar_path = _find_server_jar(realm_dir)
    if jar_path is None:
        notes.append("No server_*.jar found in the realm directory.")

    main_class = read_jar_main_class(jar_path) if jar_path is not None else None
    detected_server_type = classify_main_class(main_class)

    if has_mods_dir and detected_server_type != "fabric":
        notes.append(
            "Has a mods/ directory but the jar wasn't detected as Fabric -- "
            "could be Forge or a manifest this heuristic doesn't recognize, treat with suspicion."
        )

    return RealmInspection(
        data_dir=realm_dir.name,
        has_mods_dir=has_mods_dir,
        jar_path=jar_path,
        jar_main_class=main_class,
        detected_server_type=detected_server_type,
        online_mode_currently_true=_read_online_mode(realm_dir / "server.properties"),
        current_port=_read_server_port(realm_dir / "server.properties"),
        has_paper_global_yml=(realm_dir / "config" / "paper-global.yml").exists(),
        notes=notes,
    )


def is_velocity_compatible(inspection: RealmInspection) -> bool:
    """True only for a positively-detected Paper server -- vanilla/unknown are never compatible."""

    return inspection.detected_server_type == "paper"


def require_velocity_compatible(inspection: RealmInspection) -> None:
    """Raise IncompatibleRealmError unless the realm was positively detected as Paper."""

    if not is_velocity_compatible(inspection):
        raise IncompatibleRealmError(
            f"'{inspection.data_dir}' was detected as '{inspection.detected_server_type}', "
            "not Paper -- Velocity's modern forwarding only works with Paper/Spigot-family "
            "servers. This needs a manual conversion, not automatic activation -- see "
            "docs/workflows/convert-engine.md."
        )
