# Epic BAK — Backup & Restore

Scope: `models/backup_result.py`, `services/backup_service.py`,
`commands/backup.py`.

## Purpose

Point-in-time snapshots of a realm's live data directory, independent of
git — world saves are large, binary, and change on autosave, so they were
deliberately kept out of the tracked repo tree (see
[deployment-workflow.md](../architecture/deployment-workflow.md) for why
the two-tree split replaced an earlier `git stash`-based design).

## Current design

- **One archive per run**: `backup_server()` tars `data_root/<data_dir>`
  into `backups_root/<server_id>-<UTC timestamp>.tar.gz`
  (`YYYYMMDDTHHMMSSZ`), then writes a sibling `.sha256` file in
  `sha256sum`-compatible format (`<digest>  <filename>`). No pruning or
  retention policy — every run adds a new archive, old ones are never
  deleted automatically.
- **Integrity, not encryption**: the sha256 exists to detect corrupt
  archives before a restore is attempted, not for security. Restoring is
  manual today — untar the archive over the realm's data directory after
  verifying the checksum (see the rollback section of
  [deployment-workflow.md](../architecture/deployment-workflow.md)) — there
  is no `minecraftmgr backup restore` command yet.
- **`resolve_server_data_dir()`** centralizes `data_root / entry.data_dir`
  so backup and any future restore/inspect logic resolve the same path the
  same way, rather than each call site reimplementing the join.
- **Batch isolation**: `backup_servers()` (used by `backup run --all`)
  catches `BackupError` per realm and collects `(server_id, reason)`
  failures instead of aborting the whole batch on the first missing data
  directory. `commands/backup.py` prints each success/failure line, then
  exits 1 only if `failures` is non-empty — so a single misconfigured
  realm doesn't block backing up the rest.
- **CLI surface** (`commands/backup.py`): `backup run <server_id>` or
  `backup run --all` — exactly one of the two is required (`bool(server_id)
  == all_servers` is the XOR check that rejects both-or-neither).

## Open work

- No restore command — restore is a manual runbook step today.
- No retention/pruning policy for old archives in `backups_root`.
- No dry-run or size-estimate before archiving (relevant once realms have
  large world saves and `backups_root` disk space becomes a concern on
  oscar).
