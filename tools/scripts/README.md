# tools/scripts/

Oscar-side Minecraft automation, imported verbatim from oscar on 2026-08-18
(see [docs/architecture/oscar-migration-plan.md](../../docs/architecture/oscar-migration-plan.md#3-port-the-scripts)
for the full backstory). **Nothing here has been rewritten yet** — these are
straight copies of what's actually running, with a short provenance comment
added to the top of each file. Redeploying them onto oscar in place of the
untracked originals is a separate manual step: see
[docs/workflows/redeploy-oscar-scripts.md](../../docs/workflows/redeploy-oscar-scripts.md).

The plan is to work through the "known issues" column below incrementally,
one script at a time, rather than rewrite everything at once.

| Script | Original oscar path | Status | Known issues |
|---|---|---|---|
| `start_all_minecraft_servers.sh` | `/opt/mc/Scripts/` | Live (cron/manual) | Hardcoded `servers=("gravestone_26_1_2")` — only starts one realm. Should loop over `minecraftmgr server list --active-only` instead. |
| `stop_all_minecraft_servers.sh` | `/opt/mc/Scripts/` | Live (cron/manual) | Same hardcoded-array issue as above. |
| `scafold_new_minecraft_server.sh` | `/opt/mc/Scripts/` | Superseded, kept for reference | Replaced by `minecraftmgr realm provision`/`realm activate` ([PROV-design.md](../../docs/epics/PROV-design.md)), confirmed working live on oscar. Still assumes the pre-migration `/srv/minecraft` path. Not planned to be revived — kept here only so the old approach isn't lost. |
| `scafold_help.txt` | `/opt/mc/Scripts/` | Superseded, kept for reference | Usage example for the script above. |
| `config_ufw_rules.sh` | `/opt/mc/Scripts/` | Live (manual, run by hand) | Hardcoded `MINECRAFT_PORTS=(26005 26010)` — doesn't cover realms added since, and doesn't know about the shared Velocity port (`25565`). Also mixes in non-Minecraft rules (Samba, Plex, Docker) — fine for oscar as a whole, but worth deciding whether that scope belongs in this repo. |
| `minecraft_all_in_one_backup_v1.sh` | `/opt/mc/Scripts/` | Live (cron, nightly per [[oscar_migration_status]]) | Superseded in spirit by `minecraftmgr backup run --all` (see [BAK.md](../../docs/epics/BAK.md)), but that command doesn't yet have retention/pruning ("keep last 3") or a stop/restart cycle, so this is still the one actually cron'd. Don't retire until `minecraftmgr backup` covers both. |
| `minecraft_single_backup.sh` | `/opt/scripts/` | Newer variant, unclear if cron'd | `BASE_DIR="/srv/minecraft"` is stale post-migration (real path is `/opt/mc`) — would fail as-is against any realm today. Needs the same path fix as everything else, plus a decision on whether this replaces the all-in-one script or the two get merged. |
| `extract-user-data.py` | `/opt/mc/<realm>/` (one copy per realm) | Live, was triplicated | Was byte-identical in `arbor_1_21_10`, `gravestone_26_1_2`, `river_1_21_1` — consolidated to this one tracked copy. Needs a decision on where the deployed copy should live (once per realm again via a deploy step, or a single shared location realms are pointed at). |

## Explicitly not imported

Found on oscar but deliberately left out — nothing here is lost, just not
brought into this repo:

- `/opt/mc/Scripts/start_all_minecraft_servers.sh.old`, `/opt/mc/Scripts/sync.ffs_db`
  — cruft (stale precursor script, FreeFileSync database file).
- `/opt/scripts/minecraft_all_in_one_backup_v1.sh`, `/opt/scripts/config_ufw_rules.sh`
  — stale/duplicate copies of the two files already imported above from
  `/opt/mc/Scripts/` (the `/opt/scripts/` copy of the backup script still
  points at the pre-migration `/srv/minecraft` path).
- `/opt/scripts/archived-minecraft-scripts/*` (7 files: old versions of the
  backup and zip scripts) — these already live inside the user's separate
  `mikemmattinson/Scripts` GitHub repo, which has its own git history and
  its own archive convention. Out of scope for MinecraftMgr.
- `/opt/ddns/cloudflare-ddns.sh` — described in
  [oscar-realm-hosting.md](../../docs/architecture/oscar-realm-hosting.md)
  but never actually deployed; `/opt/ddns/` doesn't exist on oscar. Nothing
  to import.

## Also worth knowing

`/opt/scripts/` on oscar is a much larger personal script library (photo/media
reorg, symlink tooling, zip utilities, its own README/CHANGELOG/tests) that
is **already** its own git repo (`github.com/mikemmattinson/Scripts`),
unrelated to Minecraft. Only the Minecraft-specific files inside it were
pulled into this repo — the rest was left untouched.
