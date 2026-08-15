"""Tests for the servers.json registry service."""

from __future__ import annotations

import pytest

from minecraftmgr.config.settings import Settings
from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.registry_service import (
    RegistryError,
    add_server,
    list_servers,
    load_registry,
    remove_server,
    update_server,
)


def _entry(server_id: str, **overrides: object) -> ServerEntry:
    fields = {
        "server_id": server_id,
        "name": server_id.title(),
        "status": "active",
        "port": 25565,
        "minecraft_version": "1.21.10",
        "server_type": "paper",
        "jar_source": "",
        "data_dir": server_id,
        "created": "2026-08-15T21:00:00+00:00",
        "notes": "",
    }
    fields.update(overrides)
    return ServerEntry(**fields)


def test_load_registry_missing_file_returns_empty(settings: Settings) -> None:
    """A missing servers.json is treated as an empty registry, not an error."""

    assert load_registry(settings) == {}


def test_add_then_list_servers(settings: Settings) -> None:
    """Added realms round-trip through the registry file, sorted by id."""

    add_server(settings, _entry("river"))
    add_server(settings, _entry("gatorland"))

    servers = list_servers(settings)

    assert [server.server_id for server in servers] == ["gatorland", "river"]


def test_add_duplicate_server_raises(settings: Settings) -> None:
    """Adding the same server_id twice is rejected."""

    add_server(settings, _entry("gatorland"))

    with pytest.raises(RegistryError):
        add_server(settings, _entry("gatorland"))


def test_list_servers_active_only(settings: Settings) -> None:
    """active_only filters out inactive realms."""

    add_server(settings, _entry("gatorland", status="active"))
    add_server(settings, _entry("arbor", status="inactive"))

    servers = list_servers(settings, active_only=True)

    assert [server.server_id for server in servers] == ["gatorland"]


def test_remove_server(settings: Settings) -> None:
    """Removing a realm drops it from the registry."""

    add_server(settings, _entry("gatorland"))
    remove_server(settings, "gatorland")

    assert list_servers(settings) == []


def test_remove_missing_server_raises(settings: Settings) -> None:
    """Removing a realm that was never registered is an error."""

    with pytest.raises(RegistryError):
        remove_server(settings, "missing")


def test_update_server_changes_fields(settings: Settings) -> None:
    """update_server only touches the fields passed in."""

    add_server(settings, _entry("gatorland", notes="old"))

    updated = update_server(settings, "gatorland", status="inactive", notes="retired")

    assert updated.status == "inactive"
    assert updated.notes == "retired"
    assert updated.name == "Gatorland"
