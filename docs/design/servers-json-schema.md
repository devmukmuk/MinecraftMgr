# docs/design/servers-json-schema.md

Schema for the tracked realm registry, `servers.json`, resolved relative to
the repo root (see `resolve_servers_json_path()` in
`src/minecraftmgr/config/settings.py`). Read/written through
`src/minecraftmgr/services/registry_service.py` and modeled by
`ServerEntry` (`src/minecraftmgr/models/server_entry.py`).

## Shape

A single JSON object keyed by `server_id`. Each value is the entry's fields
(the id itself is the key, not repeated inside the value):

```json
{
  "gatorland": {
    "name": "Gatorland",
    "status": "active",
    "port": 25566,
    "minecraft_version": "1.21.10",
    "server_type": "paper",
    "jar_source": "https://papermc.io/downloads",
    "data_dir": "gatorland",
    "created": "2026-08-15T21:00:00+00:00",
    "notes": ""
  },
  "arbor": {
    "name": "Arbor",
    "status": "inactive",
    "port": 25569,
    "minecraft_version": "1.21.10",
    "server_type": "paper",
    "jar_source": "https://papermc.io/downloads",
    "data_dir": "arbor",
    "created": "2026-05-01T10:00:00+00:00",
    "notes": "retired, kept for backup history"
  }
}
```

## Fields

| Field               | Type | Notes                                                                 |
|---------------------|------|------------------------------------------------------------------------|
| `name`               | str  | Display name                                                          |
| `status`             | str  | `active` or `inactive`; `minecraftmgr server list --active-only` filters on this |
| `port`               | int  | Backend port on oscar, bound to `127.0.0.1` behind Velocity (see [oscar-realm-hosting.md](../architecture/oscar-realm-hosting.md)) |
| `minecraft_version`  | str  | Minecraft version the realm runs                                      |
| `server_type`        | str  | `paper`, `vanilla`, `fabric`, `forge`, ...                            |
| `jar_source`         | str  | Where the server jar comes from (URL or note)                         |
| `data_dir`           | str  | Folder name under `data_root` holding the live server (world, jar, `server.properties`) |
| `created`             | str  | ISO 8601 timestamp, set when the realm is registered                  |
| `notes`               | str  | Free-text, defaults to `""`                                           |

## Conventions

- `server_id` (the JSON key) is immutable — remove and re-add rather than
  renaming.
- `save_registry()` always writes keys sorted alphabetically, so diffs stay
  stable across machines.
- A `forced-hosts` entry in `velocity.toml` and a Cloudflare CNAME both key
  off `server_id`, so keep it matching the subdomain
  (`gatorland` → `gatorland.gamenightbymike.com`).
