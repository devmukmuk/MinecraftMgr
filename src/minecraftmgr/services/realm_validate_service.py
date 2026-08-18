"""Validate a realm's start.sh against the canonical tools/templates/start.sh.template.

Checks are deliberately narrow: the IPv4 flag (oscar's broken outbound IPv6
silently breaks Mojang auth without it -- see oscar-migration-plan.md) and
the port matching servers.json (the registry is authoritative for port,
start.sh's own PORT= is what actually wins at boot per
realm_inspect_service's port-mismatch handling, so drift here is real).

MEM_MIN/MEM_MAX are deliberately NOT validated against anything -- they
aren't modeled in ServerEntry yet (see oscar-migration-plan.md's open work),
so there's no authoritative value to check against. fix_start_sh() preserves
whatever the file already has for those rather than inventing a number.
"""

from __future__ import annotations

from pathlib import Path

from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.models.start_sh_validation import StartShValidation
from minecraftmgr.services.realm_scaffold_service import render_start_sh

_DEFAULT_MEM_MIN = "2G"
_DEFAULT_MEM_MAX = "4G"


def _parse_assignment(lines: list[str], var: str) -> str | None:
    prefix = f"{var}="
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped.split("=", 1)[1].strip().strip("\"'")
    return None


def validate_start_sh(realm_dir: Path, server: ServerEntry) -> StartShValidation:
    """Check a realm's start.sh for drift from the canonical template."""

    start_sh_path = realm_dir / "start.sh"

    if not start_sh_path.exists():
        return StartShValidation(
            data_dir=server.data_dir,
            exists=False,
            has_ipv4_flag=False,
            port_matches_registry=False,
            current_mem_min=None,
            current_mem_max=None,
            issues=["start.sh does not exist"],
        )

    text = start_sh_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    mem_min = _parse_assignment(lines, "MEM_MIN")
    mem_max = _parse_assignment(lines, "MEM_MAX")
    port_str = _parse_assignment(lines, "PORT")
    current_port = int(port_str) if port_str and port_str.isdigit() else None

    has_ipv4_flag = "preferIPv4Stack=true" in text
    port_matches = current_port == server.port

    issues: list[str] = []

    if not has_ipv4_flag:
        issues.append(
            "missing -Djava.net.preferIPv4Stack=true "
            "(oscar's broken outbound IPv6 breaks Mojang auth without it)"
        )

    if not port_matches:
        issues.append(
            f"start.sh PORT={current_port} does not match servers.json port={server.port}"
        )

    return StartShValidation(
        data_dir=server.data_dir,
        exists=True,
        has_ipv4_flag=has_ipv4_flag,
        port_matches_registry=port_matches,
        current_mem_min=mem_min,
        current_mem_max=mem_max,
        issues=issues,
    )


def fix_start_sh(realm_dir: Path, server: ServerEntry, validation: StartShValidation) -> None:
    """Rewrite start.sh from the canonical template.

    Preserves the existing MEM_MIN/MEM_MAX if start.sh had them, falling
    back to the same defaults realm_scaffold_service uses for a brand-new
    realm -- never silently changes a realm's memory allocation.
    """

    rendered = render_start_sh(
        name=server.data_dir,
        port=server.port,
        mem_min=validation.current_mem_min or _DEFAULT_MEM_MIN,
        mem_max=validation.current_mem_max or _DEFAULT_MEM_MAX,
    )

    start_sh_path = realm_dir / "start.sh"
    start_sh_path.write_text(rendered, encoding="utf-8")
    start_sh_path.chmod(0o770)
