"""Tests for ServerEntry (de)serialization."""

from __future__ import annotations

from minecraftmgr.models.server_entry import ServerEntry


def test_to_dict_from_dict_roundtrip() -> None:
    """to_dict/from_dict roundtrips a ServerEntry, server_id passed separately."""

    entry = ServerEntry(
        server_id="gatorland",
        name="Gatorland",
        status="active",
        port=25566,
        minecraft_version="1.21.10",
        server_type="paper",
        jar_source="https://papermc.io/downloads",
        data_dir="gatorland",
        created="2026-08-15T21:00:00+00:00",
        notes="test realm",
    )

    rebuilt = ServerEntry.from_dict(entry.server_id, entry.to_dict())

    assert rebuilt == entry


def test_from_dict_applies_defaults() -> None:
    """from_dict fills in defaults for optional fields."""

    entry = ServerEntry.from_dict("river", {"name": "River", "port": 25567})

    assert entry.status == "active"
    assert entry.server_type == "paper"
    assert entry.data_dir == "river"
    assert entry.notes == ""
