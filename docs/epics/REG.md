# Epic REG — Realm Registry

Scope: `servers.json`, `models/server_entry.py`, `services/registry_service.py`,
`commands/server.py`.

## Purpose

The source of truth for which realms exist, independent of whether they're
currently running or how their world data is laid out on disk. Everything
else (backups, deploys) looks realms up here rather than scanning
`data_root` directly.

## Current design

- **Storage shape**: `servers.json` is a single JSON object keyed by
  `server_id`, values are the entry fields — see
  [servers-json-schema.md](../design/servers-json-schema.md) for the full
  field table. `server_id` is treated as immutable; renaming means
  remove + re-add, not an update, because `server_id` also has to match
  the Velocity `forced-hosts` entry and Cloudflare CNAME for that realm
  (see [oscar-realm-hosting.md](../architecture/oscar-realm-hosting.md)).
- **`ServerEntry`** is a frozen dataclass with `to_dict`/`from_dict`,
  matching the JSON shape exactly except that `server_id` is the dict key
  rather than a field inside the value (`to_dict()` excludes it).
- **`registry_service`** is the only thing that reads/writes `servers.json`.
  `save_registry()` always sorts by `server_id` before writing, so registry
  diffs stay small and stable regardless of which machine or command
  produced them. Updates go through `update_server()`, which uses
  `dataclasses.replace()` against the frozen `ServerEntry` rather than
  mutating fields — keeps `ServerEntry` immutable everywhere else in the
  codebase.
- **Failure mode**: `RegistryError` for both "already exists" (`add`) and
  "not found" (`remove`/`update`) — callers in `commands/server.py` catch
  it, print in red, and exit 1, rather than letting a traceback surface.
- **CLI surface** (`commands/server.py`): `add`, `list` (`--active-only`
  filter), `remove` (confirms unless `--yes`), `update` (only the fields
  passed as options change — `None` means "leave alone", so `update`
  builds a `changes` dict of only the non-`None` options before calling
  `update_server(**changes)`).

## Open work

- No `server show <id>` command for a single realm's full detail — `list`
  only prints a subset of fields (no `jar_source`, `data_dir`, `notes`,
  `created` in the table).
- No validation that `port` is unique across entries, or that `data_dir`
  doesn't collide with another realm's. Matters more than it sounds: a real
  collision confirmed live on oscar (2026-08-16) — `poop_1_21_1` and
  `poop_1_21_3` both actually bind `26111` — came from realms not even in
  the registry yet, so a `servers.json`-only uniqueness check wouldn't have
  caught it. (`arbor_1_21_10` really was also reusing `gravestone`'s `26005`
  at the time this was first found, confirmed via its `start.sh`; it's since
  been moved to `26124` by hand, unrelated to any tooling here.) See
  [PROV-design.md](PROV-design.md)'s "Future work" section for a proposed
  `realm audit-ports` command that scans actual realm folders instead.
- **`server.properties`'s `server-port` isn't reliable on its own** — every
  realm's `start.sh` except `cave_1_20_4`'s (which has no `start.sh` at all)
  passes an explicit `--port $PORT` on the command line, which wins over
  whatever `server.properties` says. `poop_1_21_1`/`poop_1_21_3` show this
  clearly: `server.properties` says `28314` for both, but the real, live,
  actually-colliding port for both is `26111` from `start.sh`. Any future
  port-auditing tool (registry-based or the proposed `realm audit-ports`)
  has to read both `server.properties` *and* grep each realm's `start.sh`
  for a `--port` override, or it will report ports that were never
  actually live.
