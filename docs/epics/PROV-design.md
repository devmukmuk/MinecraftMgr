# Epic PROV — Realm Provisioning

Scope: `models/realm_inspection.py`, `services/realm_inspect_service.py`,
`services/jar_cache_service.py`, `services/realm_scaffold_service.py`,
`services/provision_service.py`, `services/realm_handoff_service.py`,
`commands/realm.py`, `tools/templates/`.

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
- Velocity itself runs as a `minecraft`-owned `screen -dmS velocity_proxy`
  session, **not systemd** (despite what earlier docs assumed) — confirmed
  via `ps aux`. Restarting it to pick up new `[servers]`/`[forced-hosts]`
  entries needs the same `minecraft`-user-only rule as any realm.
- `/opt/mc/_proxy/` (containing `velocity.toml`) is `mike`-writable, though —
  so *editing* that file doesn't need the `minecraft` boundary, only
  *restarting* Velocity does.
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
  conversion process used for `gravestone`.

## Explicitly out of scope for this epic

- Calling PaperMC's Fill API to auto-download missing jars
- Auto-converting a detected Fabric/Forge/vanilla realm to Paper
- Actually editing `velocity.toml` or restarting Velocity from inside these
  commands (printed instructions only)
- Cloudflare CNAME automation (no API token exists on oscar)
- Porting the oscar-only `start_all`/`stop_all`/`config_ufw_rules` scripts
  (separate, already-tracked in `DEP.md`)

## Open work

- Not yet deployed/run for real on oscar — code + tests only until the user
  runs it live.
- `mem_min`/`mem_max` aren't modeled in `ServerEntry` (an existing decision
  from the Velocity work, not revisited here) — `provision` takes them as
  CLI flags with defaults, doesn't persist them to `servers.json`.
- No port-uniqueness validation against other registered realms yet (same
  gap `REG.md` already flags for `server add`).
