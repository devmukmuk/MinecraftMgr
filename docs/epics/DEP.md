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
  in git history.
- **Deploy = pull, then restart**: `git push` locally → `ssh oscar` →
  `minecraftmgr backup run --all` (safety snapshot, independent of git) →
  `git pull` → `systemctl restart mc-<realm>` for whichever realms
  changed, or `mc-proxy` if `velocity.toml` changed.
- **Rollback** branches on what broke: a code/config problem is a `git
  revert`/`checkout` in `/srv/minecraft` followed by a restart (never
  touches world data); a world-data problem is restoring the affected
  realm's directory from its most recent `backups_root` archive
  ([BAK](BAK.md)) after checksum verification, unrelated to git.

## Open work

- The systemd process model described above was never actually deployed
  on oscar — real realms run under `screen`, started by hand-maintained
  scripts. [oscar-migration-plan.md](../architecture/oscar-migration-plan.md)
  documents the real layout and the plan to reconcile `/srv/minecraft`
  with the git/data split, while explicitly leaving the `screen`→systemd
  conversion as separate, later work.
- Restart is a manual step today (`screen` stop/start or `systemctl` once
  that conversion happens) — no `minecraftmgr server restart <id>` CLI
  command wraps it, so DEP still depends on shelling into oscar directly
  for that step. It also must run as the `minecraft` system user, not
  whichever user is SSH'd in — the world's lock file and other live files
  are group-read-only, so a command run as the wrong user fails with
  `AccessDeniedException` rather than actually starting the realm.
- `tools/scripts/` (oscar-side live server scripts) and `tools/python/`
  from the original project scope aren't built yet. The migration plan
  identifies which of oscar's existing `Scripts/` should be ported in
  (`start_all`/`stop_all`/`scaffold_new`/`config_ufw_rules`) once the
  `/opt/mc` split happens.
- No automated health check after a deploy (e.g. confirming a realm came
  back up and reachable) — Step 10 of the runbook is a manual
  client-connect test.
- No Velocity proxy actually runs, confirmed by getting a real realm
  connected end to end: each realm needs its own AT&T router port-forward,
  Cloudflare `SRV` record (not `CNAME` — see
  [oscar-migration-plan.md](../architecture/oscar-migration-plan.md)),
  and an explicit `ufw allow <port>/tcp` rule. None of that is automated
  yet — it's three manual dashboard/CLI steps per realm.
- Oscar's outbound IPv6 is broken, which silently breaks Mojang session
  verification unless every realm's `start.sh` forces
  `-Djava.net.preferIPv4Stack=true`. Worth fixing at the network level
  eventually, but the JVM flag is the practical fix for now.
- Oscar's `/srv/mc` checkout has no working GitHub credentials (cloned
  over plain HTTPS, no `gh` installed) — commands run on oscar that
  mutate `servers.json` (like `server add`) have no path back into git.
  The documented deploy flow is one-directional (dev box → push → oscar
  `git pull`); this needs an explicit decision — give oscar real push
  credentials, or make "mutate the registry only from the dev box" the
  actual rule.
