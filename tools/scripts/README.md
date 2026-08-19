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

**Deleted 2026-08-18**: `start_all_minecraft_servers.sh` and
`stop_all_minecraft_servers.sh` — fully superseded by `minecraftmgr realm
start --all`/`realm stop --all` (reads `servers.json` instead of a
hardcoded array), confirmed working live on oscar. Their untracked
originals still sit at `/opt/mc/Scripts/` until the broader
[redeploy-oscar-scripts.md](../../docs/workflows/redeploy-oscar-scripts.md)
cutover removes that whole directory.

| Script | Original oscar path | Status | Known issues |
|---|---|---|---|
| `scafold_new_minecraft_server.sh` | `/opt/mc/Scripts/` | Superseded, kept for reference | Replaced by `minecraftmgr realm provision`/`realm activate` ([PROV-design.md](../../docs/epics/PROV-design.md)), confirmed working live on oscar. Still assumes the pre-migration `/srv/minecraft` path. Not planned to be revived — kept here only so the old approach isn't lost. |
| `scafold_help.txt` | `/opt/mc/Scripts/` | Superseded, kept for reference | Usage example for the script above. |
| `config_ufw_rules.sh` | `/opt/mc/Scripts/` | Live (manual, run by hand) | Hardcoded `MINECRAFT_PORTS=(26005 26010)` — doesn't cover realms added since, and doesn't know about the shared Velocity port (`25565`). Also mixes in non-Minecraft rules (Samba, Plex, Docker) — fine for oscar as a whole, but worth deciding whether that scope belongs in this repo. |
| `minecraft_all_in_one_backup_v1.sh` | `/opt/scripts/` (**corrected** 2026-08-18 — see below) | Live (cron, weekly Sun 3am as `minecraft`, confirmed via log output) | Superseded in spirit by `minecraftmgr backup run --all` (see [BAK.md](../../docs/epics/BAK.md)), but that command doesn't yet have retention/pruning ("keep last 3") or a stop/restart cycle, so this is still the one actually cron'd. Don't retire until `minecraftmgr backup` covers both. |
| `minecraft_single_backup.sh` | `/opt/scripts/` | Newer variant, unclear if cron'd | `BASE_DIR="/srv/minecraft"` is stale post-migration (real path is `/opt/mc`) — would fail as-is against any realm today. Needs the same path fix as everything else, plus a decision on whether this replaces the all-in-one script or the two get merged. |
| `extract-user-data.py` | `/opt/mc/<realm>/` (one copy per realm) | Live, was triplicated | Was byte-identical in `arbor_1_21_10`, `gravestone_26_1_2`, `river_1_21_1` — consolidated to this one tracked copy. Needs a decision on where the deployed copy should live (once per realm again via a deploy step, or a single shared location realms are pointed at). |

## Verdict: replace, keep, or delete (CLI audit, 2026-08-18)

Once `tools/scripts/` existed, each script was compared against what the
`minecraftmgr` CLI (`commands/`, `services/trigger_service.py`,
`services/backup_service.py`) already does, to decide what's still needed,
what the CLI should grow to replace it, and what's simply obsolete now.

| Script | What the CLI already covers | Verdict |
|---|---|---|
| `scafold_new_minecraft_server.sh` + `scafold_help.txt` | `realm provision`/`realm activate` — confirmed live, and strictly better (jar caching, first-boot cycle, positive Paper/Fabric/vanilla detection, Velocity trust patching, handoff snippets). The old script still assumes pre-migration `/srv/minecraft` paths and knows nothing about Velocity | **Delete (OBE)** — fully superseded, not just mostly. Git history keeps a copy if ever needed; no reason to carry it forward "for reference" now that the comparison is this one-sided. |
| `config_ufw_rules.sh` | Nothing — `minecraftmgr` doesn't manage the firewall, and this script also covers Samba/Plex/Docker/SSH, well outside Minecraft's scope entirely | **Keep, not a CLI candidate** — but its Minecraft port list (`26005 26010`) is stale (predates Velocity's shared `25565`, doesn't know about newer realms). Needs a manual content update, not a rewrite. |
| `minecraft_all_in_one_backup_v1.sh` | `backup run --all` covers the tar+sha256 archive part. It does **not** cover this script's stop-before-backup, retention (keep last 3), or restart-after — none of that exists in `backup_service.py` yet | **Partial replace, keep for now** — this is the actual nightly cron job today. Retire it once `BAK` grows retention (already the plan in `oscar-migration-plan.md` Step 4), not before. |
| `minecraft_single_backup.sh` | Same gap as above (`backup run <id>` has no stop/restart/retention), plus the stale `BASE_DIR=/srv/minecraft` bug already noted | **Partial replace, keep for now** — but redundant with the all-in-one script. Open decision: does this become *the* backup script (single-realm, looped for "all") once retention lands, or do the two get merged? |
| `extract-user-data.py` | Nothing — no CLI command touches log analysis at all | **Keep as-is** — genuinely standalone, no overlap, no plan to absorb it. |

Net: two wins shipped and their scripts deleted (`realm start`/`realm
stop`, 2026-08-18 — see the "Deleted" note above), one clean deletion still
pending (the scaffold script), one no-op that just needs stale content
fixed (`config_ufw_rules.sh`), and one real open decision (which backup
script survives once `BAK` gets retention, or whether they merge).

## Explicitly not imported

Found on oscar but deliberately left out — nothing here is lost, just not
brought into this repo:

- `/opt/mc/Scripts/start_all_minecraft_servers.sh.old`, `/opt/mc/Scripts/sync.ffs_db`
  — cruft (stale precursor script, FreeFileSync database file).
- `/opt/scripts/config_ufw_rules.sh` — byte-identical duplicate of the copy
  already imported from `/opt/mc/Scripts/`.
- `/opt/mc/Scripts/minecraft_all_in_one_backup_v1.sh` — **correction,
  2026-08-18**: this (not the `/opt/scripts/` copy) is the stale duplicate
  still pointing at the pre-migration `/srv/minecraft` path. An earlier
  version of this doc had it backwards. The actually-cron'd, fixed copy
  (`BASE_DIR=/opt/mc`, confirmed live via its own log output during the
  redeploy runbook's diff-check step) is `/opt/scripts/minecraft_all_in_one_backup_v1.sh`
  — that's the one imported above.
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
