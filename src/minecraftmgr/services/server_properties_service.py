"""Check and fix a realm's server.properties against tools/templates/server.properties.standard.

The standard file lists only security/connectivity settings (behind
Velocity: online-mode=false bound to 127.0.0.1, whitelist on, RCON/query/
JMX off); gameplay settings are left to each realm. Fixing rewrites just
the listed keys in place, keeping every other line, comment and order.

For Paper realms it also checks config/paper-global.yml's Velocity trust
block (enabled, online-mode, secret matching _proxy/forwarding.secret):
with online-mode=false that block is what stops a realm accepting
unauthenticated logins.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from minecraftmgr.config.settings import get_runtime_dir
from minecraftmgr.models.properties_validation import (
    PropertiesValidation,
    PropertyIssue,
    StandardSetting,
)
from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.provision_service import patch_velocity_trust
STANDARD_TEMPLATE = get_runtime_dir() / "tools" / "templates" / "server.properties.standard"


def load_standard(port: int, template_path: Path = STANDARD_TEMPLATE) -> list[StandardSetting]:
    """Parse the standard file; the comment block right above a key is its reason."""

    settings: list[StandardSetting] = []
    comment: list[str] = []

    for raw in template_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            comment = []
        elif line.startswith("#"):
            comment.append(line.lstrip("#").strip())
        elif "=" in line:
            key, value = line.split("=", 1)
            value = value.strip().replace("__PORT__", str(port))
            settings.append(StandardSetting(key.strip(), value, " ".join(comment)))
            comment = []

    return settings


def render_standard_properties(port: int) -> str:
    """Render the standard settings as a server.properties body for a new realm."""

    return "".join(f"{s.key}={s.value}\n" for s in load_standard(port))


def read_properties(path: Path) -> dict[str, str]:
    """Read key=value pairs from a server.properties file (first occurrence wins)."""

    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values.setdefault(key.strip(), value.strip())
    return values


def _whitelist_count(realm_dir: Path) -> int | None:
    try:
        return len(json.loads((realm_dir / "whitelist.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def check_velocity_trust(realm_dir: Path, secret: str | None) -> list[str]:
    """Return problems with a Paper realm's proxies.velocity block (never prints the secret)."""

    path = realm_dir / "config" / "paper-global.yml"
    if not path.exists():
        return ["config/paper-global.yml missing (the realm needs a first boot)"]

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return [f"config/paper-global.yml unreadable: {exc}"]

    velocity = (data.get("proxies") or {}).get("velocity") or {}
    problems = []
    if velocity.get("enabled") is not True:
        problems.append("proxies.velocity.enabled is not true")
    if velocity.get("online-mode") is not True:
        problems.append("proxies.velocity.online-mode is not true")
    if secret is not None and str(velocity.get("secret", "")) != secret:
        problems.append("proxies.velocity.secret doesn't match _proxy/forwarding.secret")
    return problems


def validate_server_properties(
    realm_dir: Path, server: ServerEntry, *, velocity_secret: str | None = None
) -> PropertiesValidation:
    """Compare a realm's server.properties (and Paper Velocity trust) with the standard."""

    result = PropertiesValidation(data_dir=server.data_dir, exists=False)
    path = realm_dir / "server.properties"

    if not path.exists():
        result.warnings.append("server.properties does not exist")
        return result

    result.exists = True
    current = read_properties(path)

    for setting in load_standard(server.port):
        if current.get(setting.key) != setting.value:
            result.issues.append(
                PropertyIssue(setting.key, current.get(setting.key), setting.value, setting.reason)
            )

    whitelisted = _whitelist_count(realm_dir)
    if whitelisted == 0:
        result.warnings.append(
            "whitelist.json is empty: with white-list=true nobody can join until players are "
            "added (see docs/workflows/modify-whitelist.md)"
        )

    if server.server_type == "paper":
        result.velocity_issues = check_velocity_trust(realm_dir, velocity_secret)

    return result


def fix_server_properties(realm_dir: Path, issues: list[PropertyIssue]) -> None:
    """Set the issues' keys to their standard values in place; append any that are missing."""

    path = realm_dir / "server.properties"
    wanted = {issue.key: issue.expected for issue in issues}
    raw = path.read_bytes().decode("utf-8", errors="replace")
    newline = "\r\n" if "\r\n" in raw else "\n"

    lines = raw.splitlines()
    done: set[str] = set()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in wanted and key not in done:
            lines[index] = f"{key}={wanted[key]}"
            done.add(key)

    lines.extend(f"{key}={value}" for key, value in wanted.items() if key not in done)
    path.write_bytes((newline.join(lines) + newline).encode("utf-8"))


def fix_velocity_trust(realm_dir: Path, secret: str) -> None:
    """Re-apply the Velocity trust block (enabled, online-mode, secret)."""

    patch_velocity_trust(realm_dir / "config" / "paper-global.yml", secret)
