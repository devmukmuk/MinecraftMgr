# Epic CAP — Screenshot Capture & Gallery

Scope (proposed, nothing built yet): `services/screenshot_matcher_service.py`,
`services/gallery_service.py`, `commands/screenshots.py`,
`tools/scripts/sync-screenshots.ps1`.

## Context

Idea raised 2026-08-17: organize Minecraft screenshots by realm and version,
then publish a filterable gallery linked from the realm-picker site
(`minecraft.gamenightbymike.com`).

The original framing assumed oscar already had screenshots sitting in
per-realm "logs" that just needed sorting. That's not true — Minecraft
screenshots (F2) are always a **client-side** capture, saved on whichever
machine ran the game. Confirmed live on oscar while scoping this: only two
stray files exist anywhere under `/opt/mc` today
(`arbor_1_21_10/Screenshot 2025-09-30 115705.png` and
`gravestone_26_1_2/Screenshot 2025-09-30 115705.png` — identical name and
timestamp, clearly a one-off manual drop, not a pipeline). So this epic is a
Windows → oscar → static-site pipeline, not a log-parsing script.

## Ground truth this design is based on

Confirmed live while scoping (not assumed):

- Real screenshot sources are on the Windows dev box, two of them:
  `W:\.minecraft\screenshots` (stock vanilla launcher, flat folder, filenames
  are Minecraft's own `YYYY-MM-DD_HH.MM.SS.png` format) and
  `C:\Users\mikem\AppData\Roaming\PrismLauncher\instances\<version>\minecraft\screenshots`
  (Prism, one folder per instance — the instance folder name gives a
  *version* hint, but not a *realm* hint, since multiple realms share a
  version: `cave_1_21_1`, `poop_1_21_1`, `jitterbug_1_21_1`, `river_1_21_1`
  are all `1.21.1`).
- `servers.json` already carries `minecraft_version` per realm — realm→version
  is free once a screenshot is matched to a realm.
- Realm→version can't come from the screenshot filename or folder alone, so
  matching has to fall back to timestamp correlation against each realm's own
  server logs (`<data_dir>/logs/*.log.gz`), the same join/leave line shape
  `extract-user-data.py` (a standalone script already sitting in
  `gravestone_26_1_2/` on oscar, not part of this repo) already parses:
  `[HH:MM:SS] [Server thread/INFO]: <user> joined the game`.
- No public web server currently exposes anything under `/opt/mc`. `nginx` is
  installed on oscar but **inactive**, with three stale vhosts
  (`filehost`, `dashboard`, `securecli`) left over from unrelated prior
  projects — none of them wired to a live Cloudflare Tunnel. The two live
  tunnels (`mc-trigger` → `127.0.0.1:8787`, `mission-impossible` →
  `localhost:3000`) don't route anywhere near screenshots. Publishing a
  gallery from oscar is genuinely new infra, not a reuse of something
  dormant.
- Decided with the user 2026-08-17: match by **session-window** (fuzziest,
  most automatic option, chosen over folder-based or manual-mapping
  alternatives), host images **on oscar** (not committed into the repo, not a
  separate object store), and the new public endpoint is **open, no PIN** —
  same trust level as the picker page itself.

## Current design

Three phases, each independently useful and independently confirmable before
touching the next — deliberately sequenced so the riskiest, least-reversible
step (new public DNS/tunnel exposure on oscar) comes last, after the matching
logic has been proven against real data.

### Phase 1 — Matcher + local gallery (no new exposure)

- **`services/screenshot_matcher_service.py`** (pure, injectable clock/paths,
  no subprocess): for each registered realm, parse `logs/*.log.gz` for a
  configured username's `joined the game` / `left the game` lines into a list
  of `(join_at, leave_at)` session intervals. Handle a join with no matching
  leave in the same file by extending the interval into the next log file's
  first event (log rotation mid-session). Then, for each screenshot in an
  inbox folder, find which realm's interval set contains its timestamp
  (within a small configurable slack, to absorb clock skew between the
  Windows box and oscar — both need confirming as NTP-synced and same
  timezone first). A file matching no interval is **not** dropped — it's
  classified `unmatched` and left for manual sorting (singleplayer shots,
  skew, an open session that never got a `left` line).
- Realm → version comes from `servers.json`, not from matching — a matched
  realm's `minecraft_version` is looked up directly.
- Output: files moved/copied to `_screenshots/<realm>/<version>/<original
  filename>.png` plus a `manifest.json` (`{file, realm, version, taken_at,
  matched}`) for the gallery step to consume.
- **`services/gallery_service.py`** — renders `report/index.html` from the
  manifest, styled with the same CSS variables/fonts as `site_service.py`'s
  picker page for visual consistency. Sidebar filters by realm and by
  version, pure client-side JS over an embedded JSON array — no backend.
- **Validation for this phase**: run the matcher against the two existing
  stray screenshots plus a manually-copied batch, without any new public
  exposure. Proves the session-window logic before anything is Windows- or
  DNS-facing.

### Phase 2 — Windows-side sync

- `tools/scripts/sync-screenshots.ps1` (or a `minecraftmgr screenshots sync`
  command, TBD at build time): walks both source folders, `rsync`/`scp`s
  anything not already present (dedup by filename+size) into a staging inbox
  on oscar, `/opt/mc/_screenshots/_inbox/`. Idempotent by design — safe to
  run on a schedule or by hand after a play session.
- Needs the existing `mike@oscar` Claude Code SSH key or the user's own key
  (see `[[oscar_ssh_access]]`) — no new credential.

### Phase 3 — Public exposure

- New nginx vhost on oscar serving `/opt/mc/_screenshots` (static files +
  `report/index.html`).
- New `cloudflared` tunnel ingress rule (either a new ingress line on an
  existing tunnel or a third tunnel, TBD at build time) mapping a new
  subdomain — e.g. `shots.gamenightbymike.com` — to that vhost.
- No auth, per the 2026-08-17 decision above.
- Link added from the realm-picker page (`site_service.py`) to the new
  subdomain.
- This is the phase that touches shared infra (new public DNS record, new
  tunnel ingress) — treat as its own confirmed step, not bundled into a
  Phase 1/2 PR.

## Explicitly out of scope for this epic

- Matching/tagging by *player* beyond the configured username(s) — the
  original ask ("match by user") is satisfied by realm+version scoping
  around the dev box's own screenshots, not a general multi-player
  attribution system.
- Auto-uploading screenshots from any machine other than the Windows dev box
  (no mobile/other-family-member capture pipeline).
- Editing, tagging, deleting, or curating individual screenshots through the
  gallery UI — Phase 1's gallery is read-only/generated, not an admin tool.
- PIN-gating or any other access control on the Phase 3 endpoint (revisit
  only if it becomes a real problem in practice).

## Open questions to resolve before/while building

- Exact username(s) to match against in realm logs (single Mojang account
  assumed, not yet confirmed against `usercache.json` for every realm).
- Confirm oscar and the Windows dev box are both NTP-synced and on the same
  timezone, to size the matching slack correctly.
- Final choice between a `minecraftmgr screenshots sync` Typer command vs. a
  standalone PowerShell script for Phase 2 — deferred to build time, doesn't
  affect Phase 1's design.
- Phase 3's exact tunnel/subdomain shape (new ingress line vs. new tunnel) —
  deferred to when Phase 3 actually starts.
