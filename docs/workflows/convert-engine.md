# Convert a realm's server engine (vanilla/Fabric/Forge → Paper)

**Automation status:** Deliberately manual/guided — [PROV-design.md](../epics/PROV-design.md)'s
"Explicitly out of scope" section rules out auto-converting a detected
non-Paper realm on purpose. `realm activate` (and `require_velocity_compatible()`
underneath it) refuses to touch anything that isn't positively detected as
Paper rather than attempting this itself — a mod removal or world-format
migration is exactly the kind of change that deserves a human watching it
happen, not a script deciding to drop a player's mod for them.

This is written up here because it's only ever existed as narrative inside
[oscar-migration-plan.md](../architecture/oscar-migration-plan.md)'s
"Converting both realms to Paper" section (the real gravestone/jitterbug
conversion) — generalized into a repeatable runbook.

## When to use

`realm inspect <data_dir>` or `realm activate <data_dir>` reported a realm
as `vanilla`, `fabric`, or `forge`, and you want it Velocity-compatible.
This is the *only* direction this project has ever needed or documented —
see [the other direction](#what-about-paper--vanilla) below for why.

## Prerequisites

- Read [PAPER.md](../PAPER.md) first if "why does this even matter" isn't
  already clear — the short version is Velocity's forwarding protocol
  simply doesn't exist for vanilla/Fabric/Forge, so this isn't optional
  for a realm going behind the proxy.
- Decide up front whether losing Fabric/Forge mods is acceptable. **This
  conversion drops all mods** — there's no compatibility shim for
  server-required mods through Velocity (see the "modded realm exception"
  in [oscar-realm-hosting.md](../architecture/oscar-realm-hosting.md)). If
  the mods are the point of the realm, converting to Paper isn't the right
  move — keep it on its own dedicated port instead, outside Velocity
  entirely.
- A checksum-verified Paper jar for the target Minecraft version, per
  [PAPER.md](../PAPER.md#1-where-to-get-a-paper-server-jar).

## Steps

As the `minecraft` user on oscar — world files under a live realm are
commonly `-rw-------` and owned by `minecraft` (confirmed on gravestone's
`level.dat`), so `mike` genuinely cannot read them, running or not; this
whole conversion has to happen from the `minecraft` shell, not just the
start/stop parts:

```bash
sudo -iu minecraft
```

**1. Stop the realm gracefully, and confirm it's actually gone:**

```bash
screen -S <data_dir> -p 0 -X stuff "save-all$(printf '\r')"
sleep 2
screen -S <data_dir> -p 0 -X stuff "stop$(printf '\r')"
sleep 10
pgrep -af server_<data_dir>.jar   # must print nothing before continuing
```

Graceful `stop` doesn't always take — if the process is still there,
`kill <pid>` (or `kill -9` if plain `kill` doesn't clear it) and re-check
with `pgrep`. Starting the new jar while the old process still holds the
world's lock file fails with a `LockException`, not a helpful message
naming the real cause.

**2. Back it up before touching anything.** Non-optional — this is a
same-tier risk to [update-jar-version.md](update-jar-version.md)'s "don't
skip the backup" warning, for the same reason (world-format migration is
happening in step 4, not just a jar swap):

```bash
cd /opt/mc/<data_dir>
tar czf /mnt/backup/minecraft/<data_dir>_pre-paper-convert_$(date +%Y%m%d_%H%M%S).tar.gz \
  world server.properties eula.txt ops.json whitelist.json \
  banned-ips.json banned-players.json usercache.json mods/ config/
```

**3. Swap the jar in place**, same filename `start.sh` already expects
(`server_<data_dir>.jar`) — keep the old jar rather than deleting it:

```bash
mv server_<data_dir>.jar server_<data_dir>.jar.<old_engine>-bak
cp /opt/mc/_jarcache/server_<version_with_underscores>.jar server_<data_dir>.jar
```

**Fabric/Forge only** — move `mods/` and its `config/` aside rather than
deleting; Paper ignores them either way, and this keeps the option to
revert:

```bash
mv mods mods.disabled-fabric
mv config config.disabled-fabric
```

**4. Start it and watch the log.** First boot on the new engine triggers a
one-time world-format migration (nether/end folder restructuring coming
from vanilla; Paper's own "WorldFolderMigration" pass, which gives a
30-second on-console warning to interrupt if you don't have a backup —
you do, from step 2):

```bash
screen -dmS <data_dir> ./start.sh
screen -r <data_dir>
```

Confirm it's the real world loading (an existing base, not a fresh
generation) before detaching. A couple of `Missing data pack ...` warnings
on boot are expected fallout of dropping Fabric mods and are harmless.

**5. Set up Velocity trust and finish activation.** From here it's the
same tail as [PROV-design.md](../epics/PROV-design.md) — run
`realm activate <data_dir>` now that `inspect` will positively detect
Paper, which patches `config/paper-global.yml`'s trust block and prints
the `servers.json`/`velocity.toml`/Cloudflare handoff snippets.

## Verify

- `realm inspect <data_dir>` reports `detected_server_type: paper`.
- Connect and confirm you land in the real, pre-existing world — builds,
  inventory, terrain all match what was there before.
- Once wired into Velocity (see [PROV-design.md](../epics/PROV-design.md)'s
  handoff), confirm the forced-host routes correctly — see
  [modify-local-hosts-override.md](modify-local-hosts-override.md) for
  testing this from inside the LAN.

## Gotchas

- **This is an atomic cutover, not a gradual one.** The moment
  `paper-global.yml` has `proxies.velocity.enabled: true` and the realm
  restarts, it stops accepting *any* direct connection, proxied or not —
  don't flip a realm's trust config until Velocity itself is already
  confirmed running, or the realm is stranded with zero connectivity until
  it is.
- **Java version mismatches can surface here and only here.** A given
  Paper build's bundled dependencies (e.g. the spark profiler) may not be
  tested against oscar's default `java` — if first boot crashes with a
  JVM-level error (not a normal exception), try pinning `start.sh` to an
  explicitly older JDK (`/usr/lib/jvm/java-21-openjdk-amd64/bin/java`
  instead of the bare `java` on `$PATH`) before assuming the jar itself is
  bad.
- Log rotation can hide the boot you actually care about: Paper rotates
  the *previous* run's full log into `logs/<date>-<n>.log.gz` the moment a
  *new* process claims `logs/latest.log`. If a duplicate/crashed start
  happens right after a real successful boot, `latest.log` shows only the
  tiny crash — check archive timestamps against `ps aux` start times
  before concluding a boot failed.

## What about Paper → vanilla?

This project has never done this, and there's no realistic reason to for a
realm that's going to sit behind Velocity — going backward means giving up
the one thing that makes a realm proxy-compatible in the first place.
There's no world-format risk converting Paper → vanilla the way there is
going the other direction (vanilla's format is a strict subset of what
Paper writes), so it isn't dangerous, just pointless for anything staying
behind Velocity.

If a specific realm genuinely needs to be pure vanilla (say, matching a
speedrun ruleset or a specific mod pack's expectations), the practical
move isn't "convert it in place" — it's [taking that one realm off Velocity
entirely](../architecture/oscar-realm-hosting.md#modded-realm-exception)
and giving it its own dedicated port + Cloudflare `SRV` record, the same
pattern already used for anything that can't ride the shared proxy. At
that point it's just a normal vanilla server, unrelated to any tooling in
this repo.
