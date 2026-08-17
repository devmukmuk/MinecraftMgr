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
    """Return the most recently modified server_*.jar, or None if none exist.

    Fallback only -- old realm folders can accumulate jars from other
    versions/realms (backups, copy-paste leftovers) that happen to be newer
    than the one actually in use. Prefer `_read_start_sh_jar()`, which reads
    what start.sh really launches, wherever start.sh exists.
    """

    candidates = sorted(
        realm_dir.glob("server_*.jar"), key=lambda path: path.stat().st_mtime, reverse=True
    )

    return candidates[0] if candidates else None


def _read_start_sh_jar(start_sh_path: Path, realm_dir: Path) -> Path | None:
    """Resolve the exact jar start.sh actually launches, if determinable.

    _find_server_jar()'s mtime-based glob picks whichever server_*.jar was
    modified most recently in the folder, which is not necessarily the one
    start.sh references -- confirmed live: poop_1_21_1's start.sh launches
    server_poop_1_21_1.jar (Aug 2024), but a newer, unrelated
    server_poop_1_21_3.jar (May 2025) left sitting in the same folder was
    what the glob heuristic picked instead, silently misreporting the
    realm's real engine type.
    """

    if not start_sh_path.exists():
        return None

    name: str | None = None
    jar_expr: str | None = None

    for line in start_sh_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("NAME="):
            name = stripped.split("=", 1)[1].strip().strip("\"'")
        elif stripped.startswith("JAR="):
            jar_expr = stripped.split("=", 1)[1].strip().strip("\"'")

    if jar_expr is None:
        return None

    if name is not None:
        jar_expr = jar_expr.replace("${NAME}", name).replace("$NAME", name)

    candidate = realm_dir / jar_expr
    return candidate if candidate.exists() else None


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


def _read_start_sh_port(start_sh_path: Path) -> int | None:
    """Read the PORT= assignment from start.sh, or None if absent/unset/unparseable.

    This is the value actually passed via `--port $PORT` at boot, which wins
    over whatever server.properties says -- confirmed live auditing oscar's
    sitting realms, where server.properties and start.sh disagreed for
    arbor_1_21_10, and poop_1_21_1/poop_1_21_3 both really collide at the
    start.sh value (26111), not the server.properties one (28314).
    """

    if not start_sh_path.exists():
        return None

    for line in start_sh_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("PORT="):
            value = stripped.split("=", 1)[1].strip().strip("\"'")
            return int(value) if value.isdigit() else None

    return None


def inspect_realm_dir(realm_dir: Path) -> RealmInspection:
    """Inspect a realm's data directory and positively identify its server engine."""

    notes: list[str] = []

    has_mods_dir = (realm_dir / "mods").is_dir()

    glob_jar_path = _find_server_jar(realm_dir)
    start_sh_jar_path = _read_start_sh_jar(realm_dir / "start.sh", realm_dir)

    if start_sh_jar_path is not None:
        jar_path = start_sh_jar_path
        if glob_jar_path is not None and glob_jar_path != start_sh_jar_path:
            notes.append(
                f"start.sh actually launches {start_sh_jar_path.name}, but "
                f"{glob_jar_path.name} is the most recently modified server_*.jar in this "
                f"folder -- reporting {start_sh_jar_path.name} as the real jar."
            )
    else:
        jar_path = glob_jar_path

    if jar_path is None:
        notes.append("No server_*.jar found in the realm directory.")

    main_class = read_jar_main_class(jar_path) if jar_path is not None else None
    detected_server_type = classify_main_class(main_class)

    if has_mods_dir and detected_server_type != "fabric":
        notes.append(
            "Has a mods/ directory but the jar wasn't detected as Fabric -- "
            "could be Forge or a manifest this heuristic doesn't recognize, treat with suspicion."
        )

    properties_port = _read_server_port(realm_dir / "server.properties")
    start_sh_port = _read_start_sh_port(realm_dir / "start.sh")

    if start_sh_port is not None and start_sh_port != properties_port:
        notes.append(
            f"server.properties says server-port={properties_port}, but start.sh passes "
            f"--port {start_sh_port} on the command line, which wins at boot -- reporting "
            f"{start_sh_port} as the real current_port."
        )

    current_port = start_sh_port if start_sh_port is not None else properties_port

    return RealmInspection(
        data_dir=realm_dir.name,
        has_mods_dir=has_mods_dir,
        jar_path=jar_path,
        jar_main_class=main_class,
        detected_server_type=detected_server_type,
        online_mode_currently_true=_read_online_mode(realm_dir / "server.properties"),
        current_port=current_port,
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
