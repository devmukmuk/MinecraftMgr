# Epic PROV — Realm Provisioning

Scope: `models/realm_inspection.py`, `models/start_sh_validation.py`,
`services/realm_inspect_service.py`, `services/jar_cache_service.py`,
`services/realm_scaffold_service.py`, `services/realm_validate_service.py`,
`services/capacity_service.py`, `services/provision_service.py`,
`services/realm_handoff_service.py`, `services/trigger_service.py`,
`services/trigger_daemon.py`, `commands/realm.py`, `tools/templates/`.

## Context

Registering a realm in `servers.json` alone doesn't create anything real —
the realm-picker page and `/status` will show a card for it, but the actual
Minecraft process doesn't exist until roughly 15 manual steps happen, done by
hand exactly this way converting `gravestone`/`jitterbug` earlier this
session: create the folder, find/copy the right jar, write
`start.sh`/`server.properties`/control files, do a first-boot to generate
`config/paper-global.yml`, patch its Velocity trust block, edit
`velocity.toml`, restart the proxy, add a Cloudflare CNAME, and register in
`servers.json`.

This epic covers two commands to close most of that gap:

1. **Provision a brand-new realm** — blank world, from scratch.
2. **Activate an existing realm** — one of the 7 already sitting in
   `/opt/mc` (`arbor_1_21_10`, `cave_1_20_4`, `cave_1_21_1`, `poop_1_21_1`,
   `poop_1_21_3`, `river_1_21_1`, `gatorland_26_2`) that were never migrated
   onto the Velocity/registry pattern.

Both converge on the same "make it Velocity-ready" tail.

## Ground truth this design is based on

Confirmed live on oscar (not assumed) while designing this epic:

- An existing oscar-only bash scaffold script
  (`/opt/mc/Scripts/scafold_new_minecraft_server.sh`) already does most of
  the mechanical folder setup, but is stale (old `/srv/minecraft/` paths, no
  Velocity awareness, not git-tracked, not tested). This epic effectively
  supersedes it rather than reusing it as-is.
- `config/paper-global.yml` (the file holding the Velocity trust block) only
  exists after a realm's **first boot** — this was the actual blocker hit
  converting `gravestone`/`jitterbug`.
- Velocity runs as a `screen -dmS velocity_proxy` session, **not systemd**
  (despite what earlier docs assumed). **Correction (2026-08-17):** an
  earlier version of this doc claimed that session is `minecraft`-owned as
  a hard rule, "confirmed via `ps aux`" — that was true at the one moment
  it was checked, not an enforced fact. `/opt/mc/_proxy/` is entirely
  `backup`-group-writable, and both `mike` and `minecraft` are in that
  group, so nothing actually stops either user from starting it — file
  ownership across `_proxy/`'s logs and `velocity.jar` itself was found
  genuinely mixed between both users, going back weeks. There's no
  technical wall here the way there is for a realm's own `session.lock`
  (owned by `minecraft`, group-read-only) — that's a real, enforced
  boundary; Velocity's user was just drift, not enforcement.
  **Decided going forward: `minecraft`**, purely for consistency with every
  actual realm process, not because anything requires it. Restarting it to
  pick up new `[servers]`/`[forced-hosts]` entries should go through
  `minecraft` from now on.
- `/opt/mc/_proxy/` (containing `velocity.toml`) is `mike`-writable, though —
  so *editing* that file doesn't need the `minecraft` boundary, only
  *restarting* Velocity does (by convention now, not by permission).
- **This does not extend to CAP's screenshot infrastructure**
  (`mc-screenshots-http`, `mc-screenshots-tunnel`) — those are deliberately
  `mike`-owned by design (see [CAP-design.md](CAP-design.md)'s Phase 3
  section), since they never touch realm world data and specifically avoid
  needing `minecraft`/sudo at all. Only Velocity moves to `minecraft`;
  don't "consolidate everything" past that.
- Of the 7 sitting realms: `gatorland_26_2` is a genuinely empty directory.
  `arbor_1_21_10` has a `mods/` folder (Fabric, like `gravestone` before
  conversion) and `online-mode=true` still set. `cave_1_20_4`, `cave_1_21_1`,
  `poop_1_21_1`, `poop_1_21_3`, `river_1_21_1` have no `mods/` folder but
  also still have `online-mode=true` and no Velocity trust config — engine
  type for these is otherwise unconfirmed.
- No Cloudflare API token exists anywhere on oscar, and the documented DDNS
  cron script was never actually deployed (`/opt/ddns/` doesn't exist) — so
  Cloudflare CNAME creation has no automation path today.
- `servers.json` mutations must always happen from the Windows dev box —
  oscar's checkout is HTTPS-only with no push credentials (pre-existing,
  already-tracked gap, unchanged by this epic).

## Hard constraints carried over unchanged

- Only the `minecraft` Linux user on oscar may start/stop a realm's (or
  Velocity's) `screen` session. The automation SSH key is `mike`-only and
  must never invoke `provision`/`activate` itself — these are commands the
  human runs interactively in their own `minecraft` shell, exactly like the
  trigger daemon's deployment steps.
- `provision`/`activate` never touch `servers.json` or `velocity.toml`
  themselves — they scaffold/mutate only the realm's own directory, and end
  by printing the exact `servers.json` entry, `velocity.toml` snippet, and
  Cloudflare CNAME instructions for the human (or the assistant, via the
  dev-box `mike` SSH key, for the `velocity.toml` edit specifically) to
  apply next.

## Headline correctness fix vs. the naive design

**"No `mods/` folder" does NOT mean Paper-compatible.** `jitterbug` had no
`mods/` folder and was still vanilla (incompatible with Velocity forwarding,
same as Fabric) — `servers.json` even had it mis-recorded as `paper` before
this was caught by hand. Detection must be positive, not absence-of-evidence:
read the jar's `META-INF/MANIFEST.MF` `Main-Class` via stdlib `zipfile` (no
new dependency) to actually identify Paper vs. vanilla vs. Fabric/Forge.

## Current design

**`models/realm_inspection.py`** — frozen `RealmInspection` dataclass:
`data_dir`, `has_mods_dir`, `jar_path`, `jar_main_class`,
`detected_server_type` (`paper`/`vanilla`/`fabric`/`forge`/`unknown`),
`online_mode_currently_true`, `has_paper_global_yml`, `notes`.

**`services/realm_inspect_service.py`** — pure, filesystem-only.
`inspect_realm_dir(realm_dir) -> RealmInspection` reads the jar's manifest
for positive engine-type detection. `is_velocity_compatible(inspection)` is
true **only** for a positively-detected `paper` type — vanilla and unknown
are both `False`. `require_velocity_compatible()` raises
`IncompatibleRealmError` naming the detected type otherwise.

**`services/jar_cache_service.py`** — pure, injectable fetcher,
**cache-only for v1**. `ensure_jar_cached(data_root, minecraft_version,
fetcher=None)` never touches the network by default and raises
`JarCacheMiss` with a "download it manually via the Fill API, re-run"
message if the version isn't already in `_jarcache/`. Calling PaperMC's Fill
API (`fill.papermc.io/v3/projects/...`) automatically is deliberately out of
scope here — its response shape has only been exercised manually via `curl`
this session, never automated or checksum-verified, and installing an
unverified binary as a production server jar deserves that treatment before
it's automated. The `fetcher` injection point exists so that's a clean,
low-risk follow-up later without touching call sites.

**`services/realm_scaffold_service.py`** — pure filesystem, no subprocess.
`scaffold_realm_dir()` refuses a non-empty target directory unless
`force=True` (`ScaffoldError`). Creates
`world/,logs/,crash-reports/,versions/,libraries/`, empty-array control JSON
files, `eula.txt`, renders `start.sh` from a new git-tracked
`tools/templates/start.sh.template` and `log4j2.xml` from
`tools/templates/log4j2.xml` (fulfilling the "Templating start.sh" section
`oscar-migration-plan.md` already documented but never built), and writes a
**Velocity-ready** `server.properties` directly (`online-mode=false`,
`server-ip=127.0.0.1`, `server-port={port}`) — no separate patch-after step.
The `start.sh` template preserves the real-world shape confirmed live this
session, including the mandatory `-Djava.net.preferIPv4Stack=true` flag
(oscar's broken IPv6 silently breaks Mojang auth without it).

**`services/trigger_service.py`** (extended, not forked — it already has the
right `CommandRunner`-injection pattern and screen-session logic) gains
`stop_realm()`: a graceful `stop` via screen `stuff`, falling back to
`pgrep`+`kill` if still alive after a wait — the same fallback pattern
already used by hand twice this session (jitterbug, twice).

**`services/provision_service.py`** — orchestration and the first-boot cycle,
pure with injectable clock/sleep/runner. `wait_for_ready()` polls the log for
a ready marker, but only trusts lines with mtime at or after the moment the
process started — this guards the exact stale-`latest.log` false positive
hit converting jitterbug, where a crashed duplicate-start's tiny new log hid
behind an already-rotated archive of the real successful boot. It also fails
fast with a distinct error if the process exits before the marker appears,
rather than waiting out the full timeout on a dead process. `first_boot_cycle()`
chains start → wait → stop, and deliberately does **not** auto-kill on a
timeout — it re-raises and leaves the process running for a human to inspect
via `screen -r`, rather than risking a corrupt kill mid-world-generation.

**`services/realm_handoff_service.py`** — pure text rendering, no I/O. The
exact `servers.json`/`velocity.toml`/Cloudflare copy-paste snippets, worth
its own tested module since getting them precisely right is the point of the
feature.

**`commands/realm.py`** — new Typer sub-app (`realm inspect|provision|activate`):
- `inspect <data_dir>` — read-only, works even for a realm not yet in
  `servers.json` (the point, for the 7 sitting realms).
- `provision <server_id> --name --port --mc-version [--mem-min] [--mem-max] [--force] [--yes] [--dry-run]`
  — refuses a non-empty target dir unless `--force`; never calls
  `add_server()` itself, only prints the exact `minecraftmgr server add ...`
  invocation to run from the dev box.
- `activate <data_dir> [--yes] [--dry-run]` — calls `inspect` +
  `require_velocity_compatible` as its first internal step, before any
  confirm prompt or mutation. Gets **no** override flag for a positive
  Fabric/vanilla detection — matches the "must not auto-convert" rule; it
  reports what was detected and stops, deferring to the same manual/guided
  conversion process used for `gravestone` — written up as a runbook in
  [convert-engine.md](../workflows/convert-engine.md).

## Explicitly out of scope for this epic

- Calling PaperMC's Fill API to auto-download missing jars
- Auto-converting a detected Fabric/Forge/vanilla realm to Paper
- Actually editing `velocity.toml` or restarting Velocity from inside these
  commands (printed instructions only)
- Cloudflare CNAME automation (no API token exists on oscar)
- Porting the oscar-only `start_all`/`stop_all`/`config_ufw_rules` scripts
  (separate, already-tracked in `DEP.md`)

## Verified live (Aug 16 2026)

Deployed to oscar and run for real, not just tested: `provision` scaffolded
`testrealm` from a checksum-verified real Paper 26.2 build, generated a
genuinely blank world, correctly patched `config/paper-global.yml`'s
Velocity trust block, and stopped cleanly. Registered in `servers.json`,
wired into `velocity.toml` (edited via the `mike` key, restarted by hand in
a `minecraft` shell), and started for real end-to-end through the deployed
AUTOSTART button on the picker page — confirmed via `ps aux` on oscar, not
just the page's own status report.

## `realm validate` (2026-08-18)

Found live, while replacing `start_all_minecraft_servers.sh`/
`stop_all_minecraft_servers.sh` with `realm start`/`stop --all` and fixing
the boot-time `minecraft-autostart.service` (see [DEP.md](DEP.md)): running
`start --all` for the first time ever against every registered realm
surfaced that `arbor_1_21_10`, `cave_1_21_1`, `poop_1_21_1`, and
`river_1_21_1` all have hand-edited `start.sh` files requesting
`-Xmx14G` — impossible to satisfy even one at a time on oscar's 15Gi total
RAM, let alone four at once — and none of them have the mandatory
`-Djava.net.preferIPv4Stack=true` flag `oscar-migration-plan.md` already
documented as required. Both defects were invisible until now because the
old hardcoded-array script never actually tried starting these four.

**`services/realm_validate_service.py`** — `validate_start_sh(realm_dir,
server)` checks a realm's `start.sh` against two things only: the IPv4 flag,
and whether its `PORT=` matches `servers.json` (the registry is
authoritative for port; `start.sh`'s own value is what wins at boot, per
`realm_inspect_service`'s existing port-mismatch handling). It deliberately
does **not** validate `MEM_MIN`/`MEM_MAX` against anything — those aren't
modeled in `ServerEntry` (see Open work below), so there's no authoritative
value to check against. `fix_start_sh()` regenerates the file from
`tools/templates/start.sh.template` (reusing
`realm_scaffold_service.render_start_sh()`, now public, so there's exactly
one place that knows the template's placeholders), preserving whatever
`MEM_MIN`/`MEM_MAX` the file already had — it never silently changes a
realm's memory allocation, even a wrong one like `14G`. Fixing the actual
`14G` values is a separate, deliberate decision, not something `--fix`
does automatically.

**`commands/realm.py`**'s `validate <id>|--all [--fix]` reports per-realm
issues and, with `--fix`, rewrites `start.sh` for anything found (or reports
it can't when `start.sh` doesn't exist at all — that needs
`provision`/`activate`, not `validate`).

## Capacity cap and on-demand idle eviction (2026-08-18)

Same incident, same day: since oscar can't safely run every registered
realm at once (see above), the user asked for a hard cap on concurrently
running realms with automatic eviction when someone actually needs the
room. First framing suggested a timer-driven idle reaper — corrected during
design: *"we shouldn't stop a server just because it's idle, [only]
because someone had requested another server to be started."* That's
**reactive**, not proactive: nothing ever gets stopped just for sitting
idle; a realm only gets stopped because starting a *different* realm needed
the room. No timer, no background worker, no persistent queue — a blocked
start either evicts one idle realm or fails with a clear message, and the
human retries.

**`Settings.max_running_servers`** (default `3`, `limits:` section of
`minecraftmgr.yaml`) — oscar-local like `data_root`, since the right number
depends on the box's actual RAM.

**`services/capacity_service.py`** — orchestrates existing, already-tested
`trigger_service` primitives (`realm_running`, `start_realm`, `stop_realm`)
rather than duplicating any of them:
- `connected_player_count(port)` / `is_idle(server)` — counts established
  TCP connections to the realm's own backend port via `ss` (not RCON,
  disabled on every realm today; not a Minecraft protocol client, same
  fidelity for "is anyone connected" as parsing a real status-ping
  response, much less code). Works whether or not the realm sits behind
  Velocity — Velocity keeps one backend connection open per connected
  player, so the count is accurate either way.
- `find_idle_running_realm(candidates, exclude=...)` — first running+idle
  candidate not in `exclude`.
- `start_realm_within_capacity(server, all_servers, data_root,
  max_running=..., exclude_from_eviction=...)` — the cap counts **every**
  currently-running realm regardless of `servers.json` status (it's about
  real RAM, not registry semantics — `jitterbug`, inactive but left running
  from this session's testing, counts toward the 3 same as anything else).
  At capacity with an idle candidate available, stops it and returns it (so
  callers can report what happened); at capacity with nothing idle, raises
  `CapacityError` rather than silently failing or silently doing nothing.

**`exclude_from_eviction`** exists specifically for `realm start --all`:
starting several realms in one batch shouldn't evict realm B (also a target
in the same batch) just to start realm A, then need to restart B moments
later — that's flapping, not progress. `--all` passes its whole target-id
set as `exclude_from_eviction`, so it can only evict something *outside*
the batch to make room; if nothing outside the batch is idle, remaining
targets are skipped with a warning instead of churning.

**Both call sites now go through this**: `commands/realm.py`'s `start_cmd`
(single id exits 1 on `CapacityError`; `--all` prints a yellow skip warning
and continues), and `trigger_daemon.py`'s `POST /start/<id>` (`CapacityError`
→ HTTP `503` with a JSON `error` message the picker page can show directly
— the AUTOSTART-button feedback the user asked for, no page-side polling
loop needed). A successful eviction is reported back either way (CLI:
`Stopped idle X to make room for Y`; HTTP: `{"status": "starting",
"evicted": "X"}`).

**Deliberately not made capacity-aware**: `provision`/`activate`'s own
`first_boot_cycle()` start/stop calls — provisioning a new realm is a rare,
manual, deliberate admin action, not the automated/frequent path this cap
exists to protect. Tracked as a known gap, not a bug.

## Open work

- `mem_min`/`mem_max` aren't modeled in `ServerEntry` (an existing decision
  from the Velocity work, not revisited here) — `provision` takes them as
  CLI flags with defaults, doesn't persist them to `servers.json`.
- No port-uniqueness validation against other registered realms yet (same
  gap `REG.md` already flags for `server add`) — see "Future work" below,
  this turned out to matter: a real collision exists among the unregistered
  sitting realms, `poop_1_21_1`/`poop_1_21_3` both actually binding `26111`
  (their `server.properties` both claim `28314`, but each realm's `start.sh`
  passes a `--port` override that wins over that — see the next bullet).
  `arbor_1_21_10` was also found reusing `gravestone`'s `26005` at first,
  but has since been moved to `26124` by hand.
- **`server.properties`'s `server-port` isn't trustworthy on its own** —
  confirmed live auditing the sitting realms: every `start.sh` except
  `cave_1_20_4`'s (which has no `start.sh` at all) passes an explicit
  `--port $PORT` on the command line, which overrides `server.properties`
  at boot. Any port check — including the proposed `realm audit-ports`
  below — has to read both files, or it reports ports that were never
  actually live. **Fixed** in `inspect_realm_dir()` (issue #49): it now
  reads `start.sh`'s `PORT=` and prefers it, noting the discrepancy when
  the two disagree.
- **The most-recently-modified `server_*.jar` in a folder isn't
  necessarily the one that's actually running, either** — the same class
  of bug as the port one above, found auditing `poop_1_21_1`: its
  `start.sh` launches `server_poop_1_21_1.jar` (Aug 2024), but a newer,
  unrelated `server_poop_1_21_3.jar` (May 2025) left sitting in the same
  folder was what `_find_server_jar()`'s mtime-glob picked instead —
  silently misreporting the realm's real engine type. **Fixed** alongside
  the port issue: `inspect_realm_dir()` now prefers the jar `start.sh`
  actually references (parsing its `NAME=`/`JAR=` assignments), falling
  back to the mtime-glob heuristic only when there's no `start.sh` at all.

## Future work: modifying an already-active realm

Everything above covers *creating* a realm. Once one exists and is running,
there's currently no tooling at all for changing it short of manual
stop-edit-restart on oscar — surfaced by name while first trying the
feature out. The manual procedure for each is written out in full in
[docs/workflows/](../workflows/README.md) (one runbook per workflow, each
with an automation-status line); what follows here is the proposed shape
for automating each one, not yet built:

- **Console command injection (the unifying piece)**: generalize the
  `screen -X stuff` mechanism `trigger_service.stop_realm()` already uses
  for the in-game `stop` command into a reusable
  `send_console_command(server, data_root, command, *, runner=...)`. This
  one primitive is what actually unlocks most of the list below, live, with
  no restart:
  - **Whitelist**: `whitelist add <player>` / `whitelist remove <player>` /
    `whitelist reload` are already real Minecraft console commands. A
    `minecraftmgr realm console <id> "<command>"` wrapper covers this
    immediately; a friendlier `realm whitelist add/remove <id> <player>`
    could follow later.
  - **Rules**: server-properties-level settings (difficulty, pvp,
    spawn-protection) still need stop (now `realm stop <id>`, see below) →
    edit `server.properties` → restart (`realm start <id>`). In-world
    `/gamerule` changes (keepInventory, mobGriefing, etc.) go through the
    same console injection, live, no restart.
- **Jar version update**: no command exists yet. Shape: stop the realm
  (`stop_realm`, already built) → `ensure_jar_cached()` for the new version
  (already validates Paper via the manifest check from #33) → back up the
  old jar (`.bak` suffix, same convention as the gravestone/jitterbug
  conversions) → swap it in → `server update --mc-version` → start + a
  `wait_for_ready()`-style boot check (reusable from `provision_service`,
  just without the "first boot" framing since the world already exists).
- **Port change**: no command exists yet, and it's genuinely three files
  (`server.properties`, `start.sh`, `velocity.toml`), so the shape mirrors
  `provision`'s handoff pattern exactly: a command mutates the realm's own
  `server.properties`/`start.sh`, then prints the `velocity.toml` diff and a
  reminder that both the realm and Velocity need restarting — it should
  never touch `velocity.toml` directly, same reasoning as `provision`.
- **Port-uniqueness audit**: the real collision found this session
  (`poop_1_21_1`/`poop_1_21_3`, both actually live on `26111`) came from
  *unregistered* realms, not from `servers.json` — so a useful check can't
  just validate `servers.json` entries against each other (that's a
  narrower, separate fix worth doing in `REG` regardless). It also can't
  just read `server.properties`, per the note above — `poop_1_21_1`'s and
  `poop_1_21_3`'s both claim `28314` there, a number neither of them
  actually binds. A `minecraftmgr realm audit-ports` command needs to run
  `inspect`-style discovery across every folder in `data_root` (registered
  or not) *and* check each realm's `start.sh` for a `--port` override
  before trusting `server.properties`, to catch what a registry-only or
  properties-only check can't.
- **Seed**: not a live-modification concern — a world's seed only affects
  chunks that don't exist yet, so "changing" the seed of a realm with an
  already-generated world means starting over with a blank world, not
  editing the running one. The real gap is `provision` has no `--seed`
  option at all yet (Paper just picks a random one on first boot);  adding
  one is a small, contained change to `scaffold_realm_dir()`'s
  `server.properties` rendering.
- **Name**: already works today, no new feature needed —
  `minecraftmgr server update <id> --name "..."` + `minecraftmgr web build`.
