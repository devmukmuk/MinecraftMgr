# Epic LOG — Log Reports

Scope: `models/log_reports.py`, `services/gravestone_service.py`,
`services/user_report_service.py`, `commands/gravestones.py`,
`commands/users.py`.

## Purpose

Answers that only a realm's server logs have: where a player died and never
went back for their grave, and who has played on each realm and when. Both
features were ported from the older **MineOps** project (2026-10-05), which
MinecraftMgr split off from; MineOps had them, MinecraftMgr didn't.

## Current design

- **Which logs**: a realm's logs are `<data_root>/<data_dir>/logs/`
  (`resolve_server_data_dir()` + `logs`), realms come from `servers.json`.
  Files are read oldest first: dated `*.log.gz` (their names sort by date),
  then any plain `*.log`/`*.txt`, then `latest.log` last. Order matters: a
  grave only counts as found by a found event *after* it was placed.
- **Log line shape**: `[HH:MM:SS] [Server thread/INFO]: ...`. Paper writes
  this same shape to its log files (only the console differs), so Fabric-era
  and Paper-era logs both parse.
- **`minecraftmgr gravestones scan <realm>`** (or `--logs <folder>` for any
  folder, e.g. an old copy): matches the Gravestones mod's
  `Placed <player>'s Gravestone at (x, y, z) in <dimension>` against later
  `<player> has found their grave at (x, y, z)` at the same coordinates.
  Lists the ones never found; `--player` filters (any case), `--show-found`
  also lists found ones. gravestone dropped the mod when it moved to Paper
  (2026-08-16), so new graves only appear if a gravestone mod/plugin is
  added back with the same messages; the old logs still work.
- **`minecraftmgr users report [<realm>] [--active-only]`**: every
  `<player> joined/left the game` line, grouped per realm: first day, latest
  day, number of days seen. Dated log names give the day; `latest.log` uses
  its modified time. Active realms print first.
- Unreadable files (e.g. a truncated `.gz`) and missing logs folders become
  warnings, not errors.

## Not done (from the MineOps design)

- JSON/CSV report output (`--write-report`) for automation.
- Realms not in `servers.json` (e.g. `cave_1_20_4`, `poop_1_21_3`, or
  anything moved to `/opt/mc/_archive/`) can only be scanned with
  `gravestones scan --logs`; `users report` covers registry realms only.

Base, portal and farm coordinates people asked to keep are in
[GRAVESTONES-LOCATIONS.md](../GRAVESTONES-LOCATIONS.md) (also from MineOps).
