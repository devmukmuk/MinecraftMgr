# The "___Mgr" project convention for oscar services

MinecraftMgr is the first of a planned family of projects that each manage
one service running on `oscar` from the Windows dev box — `PlexMgr`,
`BackupMgr`, `MindItMgr` (the digital-archive/photos-and-documents service
`MindIt` will eventually split off, the same way `MinecraftMgr` split off
`MineOps`), `TautulliMgr`, and whatever comes after. None of those exist yet
(checked 2026-08-18) — this doc exists so building the *next* one doesn't
mean re-deriving decisions MinecraftMgr already made the hard way, and so
oscar doesn't end up with a different, incompatible layout per project.

This is a forward-looking convention, not something already applied twice.
Treat it as a starting point for the next project, not a rule proven by
repetition yet.

## Current state vs. target, by project

Everything under "Current" below is confirmed live via SSH on 2026-08-18
(see [[oscar_ssh_access]]), not guessed — anywhere the audit didn't reach is
marked "not yet inventoried" rather than assumed.

| Project | ProjectMgr | Services | Data | Current | Future |
|---|---|---|---|---|---|
| Minecraft | MinecraftMgr | 9 realms (`screen`-managed Paper/vanilla/Fabric), the Velocity proxy, the trigger daemon, the realm-picker site | `/opt/mc` (per-realm jar/world/config), `/mnt/backup/minecraft` | Checkout live at `/srv/mc`. `tools/scripts/` imported verbatim 2026-08-18, but **not yet redeployed** — the untracked originals at `/opt/mc/Scripts/` and `/opt/scripts/` are still what actually runs | Stays at `/srv/mc` (historical exception, not renamed). Scripts cut over via [redeploy-oscar-scripts.md](../workflows/redeploy-oscar-scripts.md), then rewritten to use `server list --active-only` and one consolidated backup script |
| Plex | PlexMgr | Plex Media Server; a cron'd `compress_watch_folder_v2.sh` (confirmed live in `mike`'s crontab, `0 1 * * *`) | `/srv/plex` (library/config — already exists, `mike:backup`) | No Mgr project yet. Managed by hand; its one known script sits loose at `/srv/plex/scripts/`, untracked | `/opt/dev/PlexMgr` checkout, pointed at the existing `/srv/plex` data (never moved). `/srv/plex/scripts/` folded into PlexMgr's own `tools/scripts/` |
| Backup (cross-service) | BackupMgr | The `backupsvc` account (member of `backup`+`minecraft`+`plex`+`scriptsgrp` groups); today: `/opt/scripts/backup/*.sh` (`cloud_sync.sh`, `daily_rsync.sh`, `secondary_disk_sync.sh`) plus Minecraft's own backup scripts, now in this repo instead | `/mnt/backup` (every service's archives) | Scattered — general-purpose scripts in `/opt/scripts/backup/`, Minecraft's in `tools/scripts/` here, no shared orchestration layer | `/opt/dev/BackupMgr` for cross-service scheduling/retention only — each service keeps owning its own actual backup logic (`minecraftmgr backup`, etc.); BackupMgr orchestrates, doesn't duplicate |
| Digital archive (MindIt) | MindItMgr | Not yet inventoried on oscar | Not yet inventoried — `/opt/photo-manager` may be related, unconfirmed this session | `MindIt` exists on the dev box; no oscar-side service audit has been done | `/opt/dev/MindItMgr`, once oscar's actual photo/document service is identified |
| Tautulli | TautulliMgr | Tautulli (Plex companion/stats), already its own no-login service account | `/opt/tautulli` | No Mgr project yet, but already the cleanest precedent — runs isolated, no consolidation needed | `/opt/dev/TautulliMgr` checkout, pointed at the existing `/opt/tautulli` |

## The one principle everything else follows

**Keep the git-tracked "management" checkout separate from the service's
live data, always.** This is the same reasoning
[deployment-workflow.md](deployment-workflow.md) already lays out for
MinecraftMgr: live data is large, binary, and changes outside any deploy
(autosave, played media, synced photos — whatever the service's equivalent
is), so tracking it in git turns every deploy into a mess and every
`git status` into noise. A Mgr project's repo holds code, docs, and small
hand-authored config/registry data — never the thing it's managing.

## Where the checkout goes: `/opt/dev/<ProjectName>`, not `/srv/<short-name>`

MinecraftMgr's checkout lives at `/srv/mc`. **Don't copy that specific
path pattern** — it doesn't generalize safely. `/srv/<service>` is already
claimed by live data for at least one future case: `/srv/plex` already holds
real Plex library/config data on oscar today, so `PlexMgr` can't reuse the
`/srv/mc`-style pattern for its own checkout without colliding with data
that's already there.

`/opt/dev/<ProjectName>` has no such collision risk and is already the home
for two other personal projects on oscar (`/opt/dev/CodeIt`,
`/opt/dev/PackIt`) — use that for every future Mgr project's checkout:
`/opt/dev/PlexMgr`, `/opt/dev/BackupMgr`, `/opt/dev/MindItMgr`,
`/opt/dev/TautulliMgr`.

`/srv/mc` is a historical exception, not a mistake worth fixing — it's
stable, working, and has a redeploy runbook written against it
([redeploy-oscar-scripts.md](../workflows/redeploy-oscar-scripts.md)).
Renaming it now to match this convention would be pure churn for a pattern
that only matters once a second project actually exists.

## Live data stays exactly where it already is

A Mgr project's job is to point at its service's existing data location, not
relocate it. Each project's own `deployment-workflow.md`-equivalent doc
should record where that is, the same way this repo's
[deployment-workflow.md](deployment-workflow.md) documents `/opt/mc` as
MinecraftMgr's `data_root` — see the "Data" column in the table above for
what's confirmed so far.

## Scripts and Python environment: one per project, not shared

Each Mgr project gets its own `tools/scripts/` and its own venv, git-tracked
inside that project's own repo — not a shared cross-project scripts
location or a single shared virtualenv. Reasoning carried over from the
oscar script/venv audit done for MinecraftMgr (2026-08-18):

- A single shared venv mixes dependency sets across unrelated services
  (Minecraft management vs. Plex vs. photo/document tooling) for no real
  benefit, and risks version conflicts. `/opt/dev/CodeIt/.venv` and
  `/opt/dev/PackIt/.venv` already establish one-venv-per-project as the
  working pattern on oscar; new Mgr projects should match it, not the
  general-purpose `/opt/scripts` repo's older, currently-broken shared venv.
- When a project first imports its service's existing hand-maintained
  scripts, follow the same "bring it over as-is first, document known
  issues, clean up incrementally" approach used for
  [tools/scripts/](../../tools/scripts/README.md) here — don't rewrite
  during the import.
- Redeploying those scripts onto oscar (moving cron entries, deleting old
  untracked copies) is a manual, `sudo`-gated runbook, same shape as
  [redeploy-oscar-scripts.md](../workflows/redeploy-oscar-scripts.md).

## Oscar user accounts and groups: reuse, don't multiply

Oscar's real accounts today are `mike` (personal admin, has `sudo`),
`minecraft` (dedicated, no-sudo process owner for realm data — a boundary
this project paid to learn the hard way, see
[PROV-design.md](../epics/PROV-design.md)'s Velocity-user correction), and
`backupsvc` (a dedicated cross-service backup runner, already a member of
the `backup`, `minecraft`, `plex`, and `scriptsgrp` groups). `plex` and
`tautulli` are pure service accounts for those applications. `backup` and
`scriptsgrp` aren't accounts at all — they're shared groups `mike` and
`minecraft` already both sit in.

That's a deliberate least-privilege split, not sprawl to consolidate. For a
new Mgr project:

- If the target service already runs under its own dedicated system account
  (like `plex`, `tautulli`), keep using that account for anything that
  touches the service's live process or data — don't move it under `mike`
  for convenience.
- If the service needs a *new* isolated account the way `minecraft` is
  isolated from `mike` (i.e., something should be able to start/stop the
  service's process without full `mike` access), create one, but only if
  that isolation is actually needed — not by default.
- Prefer adding the new account to an *existing* relevant group
  (`backup`, `scriptsgrp`) over inventing a new group per project, unless
  the access pattern genuinely doesn't fit any existing group.
- The automation SSH key pattern (dedicated passphrase-less key, `mike`-only,
  documented in [[oscar_ssh_access]]) extends to every project without
  changes — one key, reused, not one per project.

## Repo conventions: each project keeps its own

`config/git/epics.txt`, the commit-message/branch-name enforcement hooks,
and the ChangeIt/FinishIt/PostMerge workflow docs are per-repo, ported from
project to project (originally from `CodeIt`, then into `MinecraftMgr` — see
[[dev_workflow]]). Each new Mgr project should port that same convention
into its own repo rather than sharing one across projects, the same way
MinecraftMgr already did.

## Status

Written 2026-08-18, immediately after building MinecraftMgr's own
`tools/scripts/` and auditing oscar's actual venv/account layout end to end.
Nothing here has been exercised on a second project yet — when the first of
`PlexMgr`/`BackupMgr`/`MindItMgr`/`TautulliMgr` actually gets built, expect
to come back and correct whatever this doc got wrong in the abstract.
