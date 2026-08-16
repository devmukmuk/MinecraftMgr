# Paper vs. vanilla, and the three Paper workflows

## Paper isn't vanilla — it only looks that way to a player

**Vanilla** is the unmodified official Mojang/Microsoft server jar
(`minecraft.net/download/server`). It implements the base game exactly to
spec, with no plugin API — the only extension points are datapacks.

**Paper** is a *different piece of server software* — a fork descended from
the Bukkit → CraftBukkit → Spigot lineage — that reimplements the same game
logic with heavy performance work (configurable per-world tick/entity
tuning via `paper-global.yml`/`paper-world-defaults.yml`) and a real
server-side plugin API. A stock Minecraft Java client connects to a Paper
server with zero changes on the client's end, so **from inside the game a
Paper server feels identical to vanilla** — same blocks, same mobs, same
recipes. That's the whole reason it's easy to assume "Paper == vanilla":
the similarity is real, it's just at the wrong layer. The server binary,
its `Main-Class`, its config surface, and what protocols it can speak are
all different underneath.

### The concrete test this project actually uses

Both jars' `META-INF/MANIFEST.MF` name a `Main-Class`:

| | `Main-Class` |
|---|---|
| Paper | `io.papermc.paperclip.Paperclip` |
| Vanilla | `net.minecraft.bundler.Main` |
| Fabric | contains `fabricmc` |
| Forge | contains `bootstraplauncher` / `fml` |

`realm_inspect_service.classify_jar()` reads this directly out of the jar
(via stdlib `zipfile`, no new dependency) rather than guessing from folder
shape — see [PROV-design.md](epics/PROV-design.md)'s "Headline correctness
fix" for why: a `mods/` folder's absence is *not* evidence of Paper, and a
filename matching the `server_<version>.jar` convention isn't proof either.

### Why the distinction matters here specifically

[Velocity](architecture/oscar-realm-hosting.md)'s "modern forwarding"
protocol — how a realm behind the proxy trusts it for the player's real
identity instead of trusting whatever connected to `127.0.0.1` directly —
is only implemented by Paper/Spigot-family servers. Vanilla and Fabric
don't speak it. A vanilla server sitting behind Velocity doesn't fail
loudly; it just doesn't correctly forward identity, which is a much worse
failure mode than a crash. This is exactly why `realm provision`/
`realm activate` (below) refuse to proceed on anything not *positively*
detected as Paper — real incident: `jitterbug` was recorded as `paper` in
`servers.json` while its jar was actually vanilla, and nothing looked wrong
until Velocity forwarding was attempted, because a direct-connect player
can't tell the difference either.

## Known gameplay differences: redstone and farms

Reddit complaints about Paper breaking big redstone builds or automatic
farms are a real, recurring thing, not exaggeration — and they come from
the same performance work that makes Paper worth running in the first
place, not from a bug:

- **Alternate redstone engine.** Paper ships a community-written redstone
  implementation (`alternate-current`) as the default instead of vanilla's
  own algorithm — faster, but a genuinely different implementation. Builds
  that lean on vanilla-specific quirks (quasi-connectivity tricks, exact
  update-order dependencies) can behave differently or break outright.
  Switchable per-world back to vanilla-exact behavior — see below.
- **Entity AI throttling** ("entity activation range") — entities far from
  any player get ticked less often, or not at all, to save CPU. A farm
  that depends on distant mobs behaving normally (falling, pathing,
  triggering something) can misbehave if the range is tuned too tight for
  that farm's layout.
- **Per-chunk entity/hopper caps** — Paper hard-caps entity count and
  hopper transfer rate per chunk specifically to stop one big farm or item
  pile from lagging the server for everyone else on it. This is often
  exactly what people are hitting on Reddit: a deliberate ceiling vanilla
  doesn't have.

### Where the knobs live

Paper builds on top of Spigot, so a realm's `config/` folder — generated on
first boot, same as `paper-global.yml`'s Velocity trust block (see
[PROV-design.md](epics/PROV-design.md)) — ends up with layered config
rather than one file:

| File | Covers |
|---|---|
| `spigot.yml` | Entity activation range, hopper transfer/check ticks, and other tuning inherited from Paper's Spigot lineage |
| `config/paper-global.yml` | Server-wide Paper settings (already patched by `provision`/`activate` for Velocity trust) |
| `config/paper-world-defaults.yml` | Per-world settings, including `redstone-implementation` (`alternate_current` vs `vanilla`) and entity-per-chunk limits |

None of this project's tooling touches `spigot.yml` or
`paper-world-defaults.yml` today — a freshly provisioned realm runs on
whatever defaults that Paper build ships with. Exact key names shift
between Paper versions more than the general shape does, so treat the
table above as "which file to open," and read the actual generated file on
the realm in question rather than trusting a hardcoded key path from here.

### If a realm hits this

1. [Stop the realm](workflows/stop-restart-server.md).
2. Edit the relevant file — most likely `redstone-implementation` in
   `config/paper-world-defaults.yml` for a broken contraption, or the
   entity-activation-range/hopper settings in `spigot.yml` for a farm
   that's underperforming or dropping mobs/items.
3. Start it back up. Most Paper config is read at startup; a few settings
   support `/paper reload` without a restart, but that command's own
   output warns it doesn't cover everything — a full restart is the safe
   default.

This is a per-realm, per-world trade-off, not all-or-nothing: dialing a
setting back toward vanilla behavior gives up some of the performance
headroom that setting existed for, but only for that one realm/world, not
project-wide.

## 1. Where to get a Paper server jar

- **Downloads page**: <https://papermc.io/downloads/paper> — pick the
  Minecraft version and build by hand.
- **Fill API** (what this project's tooling is built around):
  `https://fill.papermc.io/v3/projects/paper/versions/<mc_version>/builds`
  — returns each build's download URL and sha256 checksum. **Always verify
  the checksum** before trusting a downloaded jar as a production server —
  running an unverified binary as your server process deserves that check,
  not just a "looks fine" glance.
- **This project's cache**: `/opt/mc/_jarcache/server_<version_with_underscores>.jar`
  on oscar. `ensure_jar_cached()` looks here first and, by default, never
  touches the network — if a version isn't cached, it raises `JarCacheMiss`
  telling you to fetch it manually and drop it in, rather than silently
  pulling something unverified. Even when a jar *is* cached under the
  right filename, `ensure_jar_cached(require_paper=True)` (the default)
  re-checks its manifest before trusting it — `_jarcache` has held
  mislabeled vanilla jars under Paper-looking filenames before (confirmed
  live on oscar, issue #33/PR #34). Calling the Fill API automatically
  isn't wired up yet; see `jar_cache_service.py`'s module docstring for why.

Manual download + verify, concretely:

```bash
curl -s https://fill.papermc.io/v3/projects/paper/versions/<mc_version>/builds \
  | python3 -m json.tool | less
# find the latest build's download URL and sha256

curl -o server_<version_with_underscores>.jar -L <download_url>
sha256sum server_<version_with_underscores>.jar
# compare against the sha256 from the API response -- must match exactly

mv server_<version_with_underscores>.jar /opt/mc/_jarcache/
```

## 2. How to deploy a new Paper server

This is `minecraftmgr realm provision` — full design in
[PROV-design.md](epics/PROV-design.md), condensed here. Run as the
`minecraft` user on oscar (never the `mike` automation key — this starts a
real process):

```bash
sudo -iu minecraft
cd /srv/mc
.venv/bin/python -m minecraftmgr realm provision <server_id> \
  --name "Display Name" \
  --port <free_port> \
  --mc-version <version> \
  --yes
```

What it does, in order: confirms a checksum/engine-verified Paper jar is in
`_jarcache` (fails fast with a clear error if not — see section 1); scaffolds
the realm's data directory from `tools/templates/start.sh.template`, with
`server.properties` already set for Velocity (`online-mode=false`,
`server-ip=127.0.0.1`); boots it once to generate `config/paper-global.yml`
(only exists after first boot); patches that file's Velocity trust block;
stops it cleanly; and prints the exact `servers.json` entry, `velocity.toml`
snippet, and Cloudflare CNAME instructions to finish wiring it in from the
dev box. There's no automated port-uniqueness check yet — cross-check
`servers.json` and existing realms' `server.properties` by hand before
picking `<free_port>`.

Already have a realm's files sitting on oscar that was never registered
(one of the pre-Velocity leftovers)? Use `realm activate <data_dir>`
instead — same tail, skips scaffolding since the folder and jar already
exist, and refuses anything not positively detected as Paper rather than
attempting a silent conversion.

## 3. How to upgrade a Paper server

Full runbook: [update-jar-version.md](workflows/update-jar-version.md).
Short version: [back up first](workflows/backup-realm.md) — this is the one
edit in the whole set of realm workflows that can genuinely corrupt a
world; [stop the realm](workflows/stop-restart-server.md); verify the new
jar is really Paper using section 1's process; swap in
`server_<data_dir>.jar` (keeping the old one as `.bak`); start it back up
and watch the log for a clean boot; then, from the dev box,
`server update --mc-version` + `web build` to update the registry and
regenerate the picker site.

This isn't a single automated command yet — it's exactly the "Jar version
update" item proposed in
[PROV-design.md](epics/PROV-design.md#future-work-modifying-an-already-active-realm)'s
Future work section.

## Never downgrade

Whichever workflow you're doing: don't put an older Minecraft version's jar
back onto a world that's already been opened by a newer one. The
world-data conversion Paper (and vanilla) does on first load of a newer
version isn't reversible — going back means restoring from a
[pre-upgrade backup](workflows/restore-from-backup.md), not just swapping
the jar back.
