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

### Phase 2 — Windows-side sync (deprioritized, likely unnecessary)

**Update 2026-08-17**: while confirming Phase 1 against real data, found that
`Z:` on the Windows dev box is already a writable Samba mount of oscar's
exact `/opt/mc` (`\\192.168.1.113\Minecraft`) — same realm folders, same
real `logs/*.log.gz`. That means the manual loop (`robocopy` real
screenshots into `Z:\_screenshots\_inbox`, then `minecraftmgr screenshots
organize` / `build-gallery` with `data_root: Z:/` in `minecraftmgr.yaml`)
already works end to end today, no dedicated sync command needed. Ran for
real: 1,175 screenshots, 662 matched to a realm (arbor 525, gravestone 129,
river 6, cave 1, poop 1), 513 correctly unsorted (mostly pre-dating oscar's
current log history). A dedicated `sync-screenshots.ps1`/`minecraftmgr
screenshots sync` command is still on the table if this ever needs to run
unattended/scheduled, but isn't planned unless that becomes a real need.

Original Phase 2 plan, kept for reference if revisited:

- `tools/scripts/sync-screenshots.ps1` (or a `minecraftmgr screenshots sync`
  command, TBD at build time): walks both source folders, `rsync`/`scp`s
  anything not already present (dedup by filename+size) into a staging inbox
  on oscar, `/opt/mc/_screenshots/_inbox/`. Idempotent by design — safe to
  run on a schedule or by hand after a play session.
- Needs the existing `mike@oscar` Claude Code SSH key or the user's own key
  (see `[[oscar_ssh_access]]`) — no new credential.

### Phase 3 — Public exposure

**Revised 2026-08-17** (superseding the original nginx sketch below): nginx
is installed on oscar but its `sites-available`/`sites-enabled` are
root-owned and the service itself is disabled — `mike` (the Claude Code SSH
key's user) can't write there or start it without an interactive `sudo`
password, which the automation key can't supply. Checked live rather than
assumed. `mike` *can*, however, create Cloudflare Tunnels and route DNS
without sudo (already done twice, for `mc-trigger` and `mission-impossible`),
and already has read access to `/opt/mc/_screenshots` via the `backup`
group. So the actual plan drops nginx entirely:

- `services/screenshot_server.py` + `minecraftmgr screenshots serve`: a
  small stdlib `ThreadingHTTPServer` (`http.server.SimpleHTTPRequestHandler`
  rooted at the served directory) — no new dependency, no root needed.
- Runs on oscar as `mike` in a `screen -dmS mc-screenshots-http` session
  bound to `127.0.0.1:8899` — the same "should be a service but isn't yet"
  pattern already used for Velocity itself (`screen -dmS velocity_proxy`,
  not systemd).
- A new, dedicated Cloudflare Tunnel (`mc-screenshots`, not reusing
  `mc-trigger` or `mission-impossible` — matches the existing precedent of
  one tunnel per concern) with an ingress rule mapping
  `shots.gamenightbymike.com` → `http://127.0.0.1:8899`, run via its own
  `screen -dmS mc-screenshots-tunnel cloudflared tunnel run mc-screenshots`.
- `cloudflared tunnel route dns mc-screenshots shots.gamenightbymike.com` —
  no manual Cloudflare dashboard step needed, same as the existing tunnels.
- No auth, per the 2026-08-17 decision above.
- Link added from the realm-picker page (`site_service.py`,
  `constants.SCREENSHOTS_URL`) to `https://shots.gamenightbymike.com/report/`
  — added only after the tunnel/DNS were confirmed actually reachable, to
  avoid a dead link briefly going live on the real family-facing page.
- This is the phase that touches shared infra (new public DNS record, new
  tunnel, new always-on process on oscar) — the code (the `serve` command)
  went through the normal PR/merge cycle, but the live oscar deployment
  steps were called out and confirmed with the user before running.

Original nginx-based sketch (not used, kept for context on why it was
rejected):
- New nginx vhost on oscar serving `/opt/mc/_screenshots` (static files +
  `report/index.html`).
- New `cloudflared` tunnel ingress rule mapping a new subdomain to that
  vhost.

## Verified live (2026-08-17)

Phases 1 and 3 (Phase 2 skipped, see above) are deployed and confirmed
working end to end against real data and real public infrastructure, not
just tests:

- `screenshots organize` run for real from the Windows dev box via the
  `Z:\` Samba share against oscar's actual realm logs: 1,175 real
  screenshots, 662 matched (arbor 525, gravestone 129, river 6, cave 1,
  poop 1), 513 correctly unsorted.
- `mc-screenshots` Cloudflare Tunnel created (id
  `88628240-7ad8-442e-b86e-5eac3943b344`), config at
  `/home/mike/.cloudflared/mc-screenshots-config.yml`, DNS routed via
  `cloudflared tunnel route dns` (no manual dashboard step).
- Running on oscar as `mike` (no sudo used anywhere in this deployment) in
  two `screen` sessions: `mc-screenshots-http` (`minecraftmgr screenshots
  serve --host 127.0.0.1 --port 8899`) and `mc-screenshots-tunnel`
  (`cloudflared --no-autoupdate --config
  .../mc-screenshots-config.yml tunnel run`). **Stays this way on
  purpose** — unlike Velocity (see [PROV-design.md](PROV-design.md)'s
  "Ground truth" section, decided `minecraft` 2026-08-17), these two never
  touch realm world data, so there's no reason to route them through
  `minecraft`/sudo at all. Don't move these if a future cleanup
  standardizes other oscar processes onto `minecraft`.
- `https://shots.gamenightbymike.com/report/` confirmed reachable from a
  real external client (not just oscar's LAN), 200 with real gallery
  content.
- The picker page's new gallery link confirmed live at
  `https://minecraft.gamenightbymike.com/` (**not** the bare
  `gamenightbymike.com` apex — that domain's `mission-impossible` tunnel
  routes it to an unrelated pre-existing app on `:3000`, a mix-up worth
  remembering next time this project's public URL needs double-checking).

**Not yet done**: neither `screen` session survives an oscar reboot —
there's no systemd unit (that would need the interactive `sudo` this
deployment specifically avoided; `mc-trigger` does have systemd units, but
those were set up by the user directly, not by an SSH-key-only session).
Worth revisiting if oscar's reboot frequency ever makes that a real
problem.

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

## Open questions — resolved

- Username: `FourEight1516` (confirmed 2026-08-17, matches `usercache.json`
  on the realms tried).
- NTP/timezone skew: not separately verified, but the default 5-second slack
  produced a sane real-data result (662/1,175 matched, with the 513 misses
  explained by pre-dating oscar's log history rather than by boundary
  misses) — good enough in practice, revisit only if matches start looking
  wrong at session edges.
- Phase 2: resolved by not building it — see the Phase 2 section above.
- Phase 3's tunnel/subdomain shape: a new dedicated tunnel (`mc-screenshots`)
  and `shots.gamenightbymike.com` — see the revised Phase 3 section above.
