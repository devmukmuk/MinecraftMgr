"""Scaffold a brand-new realm's data directory: folders, control files, start.sh, server.properties.

Pure filesystem -- no subprocess, no network. The jar itself is supplied by
the caller (see jar_cache_service) rather than fetched here. Writes a
Velocity-ready server.properties directly (online-mode=false,
server-ip=127.0.0.1) since every realm this scaffolds is meant to sit
behind Velocity from its first boot -- no separate patch-after step.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from minecraftmgr.config.settings import get_runtime_dir

REALM_SUBDIRS = ("world", "logs", "crash-reports", "versions", "libraries")
EMPTY_ARRAY_CONTROL_FILES = (
    "banned-ips.json",
    "banned-players.json",
    "ops.json",
    "whitelist.json",
    "usercache.json",
)

_TEMPLATES_DIR = get_runtime_dir() / "tools" / "templates"

_EULA_CONTENT = (
    "# By changing the setting below to TRUE you are indicating your agreement to the EULA.\n"
    "# https://aka.ms/MinecraftEULA\n"
    "eula=true\n"
)


class ScaffoldError(Exception):
    """Raised when a realm directory can't be safely scaffolded."""


def render_start_sh(*, name: str, port: int, mem_min: str, mem_max: str, java_bin: str = "java") -> str:
    """Render tools/templates/start.sh.template with the given values.

    Public: reused by realm_validate_service to regenerate an *existing*
    realm's start.sh (not just brand-new ones scaffolded here), so there's
    exactly one place that knows the template's placeholder names.
    """

    template = (_TEMPLATES_DIR / "start.sh.template").read_text(encoding="utf-8")

    return (
        template.replace("__NAME__", name)
        .replace("__PORT__", str(port))
        .replace("__MEM_MIN__", mem_min)
        .replace("__MEM_MAX__", mem_max)
        .replace("__JAVA_BIN__", java_bin)
    )


def _render_server_properties(*, port: int) -> str:
    return f"server-port={port}\nserver-ip=127.0.0.1\nonline-mode=false\nenable-rcon=false\n"


def scaffold_realm_dir(
    realm_dir: Path,
    *,
    jar_path: Path,
    data_dir: str,
    port: int,
    mem_min: str = "2G",
    mem_max: str = "4G",
    java_bin: str = "java",
    force: bool = False,
) -> None:
    """Scaffold a brand-new realm's data directory. Refuses a non-empty target unless force=True."""

    if realm_dir.exists() and any(realm_dir.iterdir()) and not force:
        raise ScaffoldError(
            f"{realm_dir} already exists and is not empty (pass force=True to overwrite)"
        )

    realm_dir.mkdir(parents=True, exist_ok=True)

    for subdir in REALM_SUBDIRS:
        (realm_dir / subdir).mkdir(exist_ok=True)

    for filename in EMPTY_ARRAY_CONTROL_FILES:
        (realm_dir / filename).write_text("[]", encoding="utf-8")

    (realm_dir / "eula.txt").write_text(_EULA_CONTENT, encoding="utf-8")

    (realm_dir / "log4j2.xml").write_text(
        (_TEMPLATES_DIR / "log4j2.xml").read_text(encoding="utf-8"), encoding="utf-8"
    )

    (realm_dir / "server.properties").write_text(
        _render_server_properties(port=port), encoding="utf-8"
    )

    start_sh_path = realm_dir / "start.sh"
    start_sh_path.write_text(
        render_start_sh(
            name=data_dir, port=port, mem_min=mem_min, mem_max=mem_max, java_bin=java_bin
        ),
        encoding="utf-8",
    )
    start_sh_path.chmod(0o770)

    shutil.copy2(jar_path, realm_dir / f"server_{data_dir}.jar")
