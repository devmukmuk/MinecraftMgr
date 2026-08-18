# Epic DEP — Oscar Deployment & Hosting

Scope: Velocity proxy, systemd, Cloudflare DNS, `docs/architecture/`.

## Purpose

Getting code and world data from the Windows dev box onto `oscar` (the
home Ubuntu box that actually runs the realms), and how players reach a
realm without per-server ports or router changes.

## Current design

This epic is documentation- and infra-config-heavy rather than
`src/`-heavy — most of it is runbook, not Python:

- **Single-port fan-out**: one router port-forward (`25565`) ever, into a
  Velocity proxy on oscar that routes by the hostname the client sent.
  Backend realm servers bind `127.0.0.1` only and are never reachable
  directly from outside oscar. Adding a realm later is a backend folder +
  one `velocity.toml` line + one Cloudflare CNAME — no router change. Full
  runbook: [oscar-realm-hosting.md](../architecture/oscar-realm-hosting.md).
- **Modded exception**: Forge/NeoForge realms with server-required mods
  can't ride through Velocity's handshake, so those get their own
  dedicated port + Cloudflare `SRV` record instead — the one case where
  "one port per realm" comes back.
- **DNS**: a single Cloudflare `A` record tracks oscar's home IP via a
  cron'd DDNS script; every realm is a `CNAME` onto that one `A` record,
  so IP changes only ever need updating in one place.
- **Two-tree split on oscar** (see
  [deployment-workflow.md](../architecture/deployment-workflow.md)):
  `/srv/minecraft` is the git checkout (code, `tools/`, tracked
  `servers.json`) — no world data ever lives here. `<data_root>` (default
  `/opt/mc`) holds each realm's live jar/world/`server.properties`,
  untracked. This replaced an earlier design that kept world saves inside
  the git tree and used `git stash` before every pull — dropped because
  world saves are large, binary, autosave-churned files that don't belong
  in git history. **Live on oscar** since the migration's Step 0 (mount
  flip repointing the realm-data disk from `/srv/minecraft` to `/opt/mc`,
  fresh `/srv/mc` checkout) — this is the actual current layout, not a
  target state. See [docs/workflows/](../workflows/README.md) for the
  runbooks that operate on a realm once it's living in this layout.
- **Realm-picker site + AUTOSTART**: `minecraftmgr web build` renders
  `servers.json` into `public/index.html`, deployed on Cloudflare Workers
  (static assets, `wrangler.jsonc`) at `gamenightbymike.com`. The AUTOSTART
  button on a stopped realm's card calls a PIN-gated trigger daemon
  (`minecraftmgr trigger serve`, `User=minecraft` only) reached through a
  Cloudflare Tunnel — no port-forward. **Confirmed live end-to-end**
  (Aug 16 2026): a real button click on the deployed page started a real
  realm process on oscar, verified via `ps aux`, not just the page's own
  status report — see [PROV-design.md](PROV-design.md)'s "Verified live"
  section.
- **Deploy = pull, then restart**: `git push` locally → `ssh oscar` →
  `minecraftmgr backup run --all` (safety snapshot, independent of git) →
  `git pull` → `systemctl restart mc-<realm>` for whichever realms
  changed, or `mc-proxy` if `velocity.toml` changed.
- **Rollback** branches on what broke: a code/config problem is a `git
  revert`/`checkout` in `/srv/minecraft` followed by a restart (never
  touches world data); a world-data problem is restoring the affected
  realm's directory from its most recent `backups_root` archive
  ([BAK](BAK.md)) after checksum verification, unrelated to git.

## Related

[oscar-mgr-project-convention.md](../architecture/oscar-mgr-project-convention.md)
generalizes this epic's checkout/data-split, per-project scripts+venv, and
oscar account/group decisions into a convention for future sibling projects
(`PlexMgr`, `BackupMgr`, `MindItMgr`, `TautulliMgr`) that will each manage a
different oscar service — none of those exist yet, so treat it as a starting
point, not a proven pattern.

## Open work

- **Correction (2026-08-18)**: the systemd process model wasn't fully
  undeployed after all — `minecraft-autostart.service` (`WantedBy=
  multi-user.target`, `User=minecraft`) already existed on oscar, enabled,
  running `start_all_minecraft_servers.sh` at boot. It was just silently
  broken since the migration's Step 0 mount flip: its `ExecStart` pointed at
  `/srv/minecraft/Scripts/`, a path that hasn't existed since, so realms
  wouldn't actually auto-start after a reboot. Found and fixed by actually
  triggering it live — repointed at `/srv/mc/.venv/bin/python -m
  minecraftmgr realm start --all`, confirmed working via `journalctl -u
  minecraft-autostart.service` (correctly started every active realm not
  already running, correctly skipped the one that was). Real realms still
  run under `screen`, not native systemd services per realm — that broader
  conversion is still the separate, later work
  [oscar-migration-plan.md](../architecture/oscar-migration-plan.md)
  describes.
- Restart still isn't a single command — `realm start`/`realm stop <id>|
  --all` exist now (2026-08-18, see
  [PROV-design.md](PROV-design.md#realm-validate-2026-08-18)'s sibling
  work), so "stop then start" covers it, but there's no combined `realm
  restart <id>`. Both must still run as the `minecraft` system user, not
  whichever user is SSH'd in — the world's lock file and other live files
  are group-read-only, so a command run as the wrong user fails with
  `AccessDeniedException` rather than actually starting the realm.
- **Found running `realm start --all` live for the first time (2026-08-18)**:
  4 of the 6 active realms (`arbor`, `cave_1_21_1`, `poop_1_21_1`,
  `river_1_21_1`) have hand-edited `start.sh` files requesting `-Xmx14G` —
  impossible to satisfy on oscar's 15Gi total RAM, especially four at once —
  and none have the mandatory `-Djava.net.preferIPv4Stack=true` flag. Never
  caught before because the old hardcoded-array script never tried starting
  them. `minecraftmgr realm validate --all --fix` (new, see
  [PROV-design.md](PROV-design.md#realm-validate-2026-08-18)) now fixes the
  IPv4 flag automatically but deliberately leaves `MEM_MAX` alone rather
  than guessing — picking real memory values per realm and applying them is
  still open, manual work.
- `tools/scripts/` (oscar-side live server scripts) now exists — every
  currently-relevant script found on oscar was imported verbatim on
  2026-08-18 (`start_all`/`stop_all`/`config_ufw_rules`, both backup script
  variants, a deduplicated `extract-user-data.py`, and `scaffold_new` kept
  for reference despite being superseded by [PROV](PROV-design.md)'s
  `minecraftmgr realm provision`/`activate`). None of it has been rewritten
  yet — see [tools/scripts/README.md](../../tools/scripts/README.md)'s
  "known issues" column for what's still outstanding (hardcoded realm
  lists, stale paths, backup-script consolidation), and
  [redeploy-oscar-scripts.md](../workflows/redeploy-oscar-scripts.md) for
  cutting oscar over from the old untracked copies to this location.
- No automated health check after a deploy (e.g. confirming a realm came
  back up and reachable) — Step 10 of the runbook is a manual
  client-connect test.
- Velocity is now actually deployed (2026-08-16), but only `gravestone`
  and `jitterbug` sit behind it so far — both had to be converted from
  their original engines (Fabric and vanilla respectively) to Paper
  first, since neither Fabric nor vanilla speak Velocity's forwarding
  protocol natively. The other 7 realms are still on the old pattern:
  their own AT&T router port-forward, Cloudflare `SRV` record (not
  `CNAME`), and an explicit `ufw allow <port>/tcp` rule. None of the
  per-realm cutover to Velocity is automated yet — see
  [oscar-migration-plan.md](../architecture/oscar-migration-plan.md)'s
  Velocity proxy deployment section for the manual steps and the
  gotchas hit doing the first two.
- Oscar's outbound IPv6 is broken, which silently breaks Mojang session
  verification unless every realm's `start.sh` forces
  `-Djava.net.preferIPv4Stack=true`. Worth fixing at the network level
  eventually, but the JVM flag is the practical fix for now.
- The Cloudflare Workers project for the picker site still scans the repo
  root and pip-installs from `pyproject.toml` during CI (noise, not a
  failure — fixed the actual build failure via `wrangler.jsonc`, PR #32).
  Changing the dashboard's "Root directory" setting to `public` would stop
  that scan; not yet confirmed done.
- `pyproject.toml` has no `[project.scripts]` entry point, so the bare
  `minecraftmgr` command has never actually existed — every runbook and
  systemd unit has to use `python -m minecraftmgr` instead. Found while
  deploying the trigger daemon (its `ExecStart` assumed the entry point
  existed). Worth fixing properly at some point, low priority since the
  `python -m` form works fine everywhere it's used today.
- Oscar's `/srv/mc` checkout has no working GitHub credentials (cloned
  over plain HTTPS, no `gh` installed) — commands run on oscar that
  mutate `servers.json` (like `server add`) have no path back into git.
  The documented deploy flow is one-directional (dev box → push → oscar
  `git pull`); this needs an explicit decision — give oscar real push
  credentials, or make "mutate the registry only from the dev box" the
  actual rule.
