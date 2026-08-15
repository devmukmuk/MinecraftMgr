"""Registry service: manage the servers.json realm registry."""

from __future__ import annotations

import json
from dataclasses import replace

from minecraftmgr.config.settings import Settings
from minecraftmgr.models.server_entry import ServerEntry


class RegistryError(Exception):
    """Raised for invalid registry operations."""


def load_registry(settings: Settings) -> dict[str, ServerEntry]:
    """Load the servers.json registry, or an empty registry if it doesn't exist yet."""

    path = settings.servers_json_path

    if not path.exists():
        return {}

    data = json.loads(path.read_text(encoding="utf-8"))

    return {
        server_id: ServerEntry.from_dict(server_id, fields)
        for server_id, fields in data.items()
    }


def save_registry(settings: Settings, entries: dict[str, ServerEntry]) -> None:
    """Write the servers.json registry, sorted by server_id for stable diffs."""

    data = {
        server_id: entries[server_id].to_dict()
        for server_id in sorted(entries)
    }

    settings.servers_json_path.write_text(
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )


def list_servers(settings: Settings, *, active_only: bool = False) -> list[ServerEntry]:
    """Return registry entries, optionally filtered to active status, sorted by server_id."""

    entries = load_registry(settings)
    servers = [entries[server_id] for server_id in sorted(entries)]

    if active_only:
        servers = [server for server in servers if server.status == "active"]

    return servers


def add_server(settings: Settings, entry: ServerEntry) -> None:
    """Add a new realm to the registry."""

    entries = load_registry(settings)

    if entry.server_id in entries:
        raise RegistryError(f"Server '{entry.server_id}' already exists")

    entries[entry.server_id] = entry
    save_registry(settings, entries)


def remove_server(settings: Settings, server_id: str) -> None:
    """Remove a realm from the registry."""

    entries = load_registry(settings)

    if server_id not in entries:
        raise RegistryError(f"Server '{server_id}' not found")

    del entries[server_id]
    save_registry(settings, entries)


def update_server(settings: Settings, server_id: str, **changes: object) -> ServerEntry:
    """Update fields on an existing realm and persist the registry."""

    entries = load_registry(settings)

    if server_id not in entries:
        raise RegistryError(f"Server '{server_id}' not found")

    updated = replace(entries[server_id], **changes)
    entries[server_id] = updated
    save_registry(settings, entries)

    return updated
