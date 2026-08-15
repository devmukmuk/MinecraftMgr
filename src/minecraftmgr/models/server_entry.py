"""Data model for a single servers.json registry entry."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServerEntry:
    """A single realm's entry in the servers.json registry."""

    server_id: str
    name: str
    status: str
    port: int
    minecraft_version: str
    server_type: str
    jar_source: str
    data_dir: str
    created: str
    notes: str = ""

    def to_dict(self) -> dict:
        """Return the servers.json field shape for this entry (excludes server_id, the dict key)."""

        return {
            "name": self.name,
            "status": self.status,
            "port": self.port,
            "minecraft_version": self.minecraft_version,
            "server_type": self.server_type,
            "jar_source": self.jar_source,
            "data_dir": self.data_dir,
            "created": self.created,
            "notes": self.notes,
        }

    @staticmethod
    def from_dict(server_id: str, data: dict) -> "ServerEntry":
        """Build a ServerEntry from a servers.json entry dict."""

        return ServerEntry(
            server_id=server_id,
            name=str(data["name"]),
            status=str(data.get("status", "active")),
            port=int(data["port"]),
            minecraft_version=str(data.get("minecraft_version", "")),
            server_type=str(data.get("server_type", "paper")),
            jar_source=str(data.get("jar_source", "")),
            data_dir=str(data.get("data_dir", server_id)),
            created=str(data.get("created", "")),
            notes=str(data.get("notes", "")),
        )
