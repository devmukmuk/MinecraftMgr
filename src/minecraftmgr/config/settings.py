"""Load MinecraftMgr configuration settings.

Discovery order mirrors MineOps (see docs/design/servers-json-schema.md):
explicit path/env var, then collocated with the running script, then a user
fallback folder. `minecraftmgr.yaml` holds machine-local paths only (never
committed, since data_root differs between the Windows dev box and oscar).
`servers.json` is the tracked, version-controlled registry and is always
resolved relative to the repo root, not the local-paths file.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml


CONFIG_FILE_NAMES = ("minecraftmgr.yaml", "minecraftmgr.yml")
SERVERS_FILE_NAME = "servers.json"


@dataclass(frozen=True)
class SettingsMetadata:
    """Describe where MinecraftMgr settings were loaded from."""

    config_path: Path
    config_source: str
    defaults_created: bool


@dataclass(frozen=True)
class Settings:
    """MinecraftMgr runtime settings."""

    data_root: Path
    backups_root: Path
    servers_json_path: Path
    metadata: SettingsMetadata
    max_running_servers: int = 3


class ConfigError(Exception):
    """Raised when MinecraftMgr configuration cannot be loaded."""


def is_frozen_app() -> bool:
    """Return whether MinecraftMgr is running from a bundled executable."""

    return bool(getattr(sys, "frozen", False))


def get_runtime_dir() -> Path:
    """Return the executable folder in dist or repo root in dev."""

    if is_frozen_app():
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[3]


def get_user_config_dir() -> Path:
    """Return the default MinecraftMgr user config folder."""

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "MinecraftMgr"

    return Path.home() / ".minecraftmgr"


def default_config_data() -> dict:
    """Build the default MinecraftMgr configuration."""

    return {
        "paths": {
            "data_root": "/opt/mc",
        },
    }


def write_default_config(config_path: Path) -> None:
    """Write the default MinecraftMgr configuration file."""

    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        return

    config_path.write_text(
        yaml.safe_dump(default_config_data(), sort_keys=False),
        encoding="utf-8",
    )


def _candidate_config_files(folder: Path) -> list[Path]:
    """Return config file candidates for a folder."""

    return [folder / name for name in CONFIG_FILE_NAMES]


def find_config_file() -> tuple[Path, str, bool]:
    """Find the MinecraftMgr config file or create the default one."""

    env_config_file = os.environ.get("MINECRAFTMGR_CONFIG_FILE")
    if env_config_file:
        path = Path(env_config_file).expanduser().resolve()
        if path.exists():
            return path, "MINECRAFTMGR_CONFIG_FILE", False
        raise ConfigError(f"MINECRAFTMGR_CONFIG_FILE does not exist: {path}")

    env_config_dir = os.environ.get("MINECRAFTMGR_CONFIG_DIR")
    if env_config_dir:
        folder = Path(env_config_dir).expanduser().resolve()

        for candidate in _candidate_config_files(folder):
            if candidate.exists():
                return candidate, "MINECRAFTMGR_CONFIG_DIR", False

    runtime_dir = get_runtime_dir()
    runtime_source = "exe folder" if is_frozen_app() else "dev project folder"

    for candidate in _candidate_config_files(runtime_dir):
        if candidate.exists():
            return candidate, runtime_source, False

    user_config_path = get_user_config_dir() / "minecraftmgr.yaml"

    defaults_created = not user_config_path.exists()

    if defaults_created:
        write_default_config(user_config_path)

    return user_config_path, "default user config", defaults_created


def load_config_file(config_path: Path) -> dict:
    """Load a YAML MinecraftMgr config file."""

    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"Unable to read config file: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML config file: {config_path}") from exc

    if data is None:
        data = {}

    if not isinstance(data, dict):
        raise ConfigError(f"Config file must contain a YAML object: {config_path}")

    return data


def _resolve_path(data_root: Path, value: str) -> Path:
    """Resolve config paths relative to data_root."""

    path = Path(value).expanduser()

    if path.is_absolute():
        return path

    return data_root / path


def resolve_servers_json_path() -> Path:
    """Resolve the tracked servers.json path, relative to the repo root."""

    return get_runtime_dir() / SERVERS_FILE_NAME


def load_settings() -> Settings:
    """Load MinecraftMgr configuration settings."""

    config_path, config_source, defaults_created = find_config_file()
    data = load_config_file(config_path)

    paths = data.get("paths", {})
    limits = data.get("limits", {})

    data_root = Path(str(paths.get("data_root", "/opt/mc"))).expanduser()
    backups_root = _resolve_path(data_root, str(paths.get("backups_root", "backups")))
    max_running_servers = int(limits.get("max_running_servers", 3))

    metadata = SettingsMetadata(
        config_path=config_path,
        config_source=config_source,
        defaults_created=defaults_created,
    )

    return Settings(
        data_root=data_root,
        backups_root=backups_root,
        servers_json_path=resolve_servers_json_path(),
        metadata=metadata,
        max_running_servers=max_running_servers,
    )
