# docs/architecture/oscar-migration-plan.md

How to migrate oscar's real, in-place `/srv/minecraft` layout to the
`/srv` (git) + `/opt/mc` (live data) split described in
[deployment-workflow.md](deployment-workflow.md). That doc describes the
*target* state; this doc is the *path* from what's actually running today
to that target, plus the parts of the target state that needed correcting
once the real layout was inspected.

## Current state (as found, Aug 2026)

`/srv/minecraft` is its own mounted filesystem (a `lost+found` is present)
holding all 9 realms directly, each mixing config with world data:

- **Process model is `screen`, not systemd.** `systemctl status
  mc-gravestone` returns "could not be found" — the systemd units
  described in [oscar-realm-hosting.md](oscar-realm-hosting.md) were never
  actually rolled out. Realms are launched by `Scripts/start_all_minecraft_servers.sh`
  (detached `screen -dmS <name> ./start.sh` per realm) and stopped by
  `Scripts/stop_all_minecraft_servers.sh`. **This migration does not
  change that** — it's a separate, larger piece of work
  ([open item](#out-of-scope) below) — but the docs need to stop claiming
  systemd is in place.
- **`start_all_minecraft_servers.sh`'s `servers=(...)` array only lists
  `gravestone_26_1_2`** — the other 8 realms aren't in the automated start
  list. `servers.json` + `status: active` replaces this array as the
  source of truth once migrated.
- **Backups** are a separate nightly script
  (`Scripts/minecraft_all_in_one_backup_v1.sh`, likely cron'd, not
  confirmed) that stops each running realm, zips `server.properties`,
  `eula.txt`, `ops.json`, `whitelist.json`, `banned-ips.json`,
  `banned-players.json`, `usercache.json`, `log4j2.xml`, `start.sh`, and
  `world/` into `/mnt/backup/minecraft/<realm>_<timestamp>.zip`, keeps the
  latest 3 per realm, then restarts whatever it stopped. **`/mnt/backup`
  is a third location**, separate from both `/srv` and `/opt` — this
  becomes `backups_root` in `minecraftmgr.yaml` on oscar, not a
  subdirectory of `data_root`.
- **`templates/`** (top-level, not per-realm) is a ~800MB **jar cache** —
  pre-downloaded server jars keyed by Minecraft version
  (`server_1_13_2.jar` … `server_26_2.jar`), pulled from by
  `Scripts/scafold_new_minecraft_server.sh` when bootstrapping a new
  realm. Not git-trackable (binary, large), but not per-realm either — it
  needs a shared home under `/opt`.
- **`Scripts/`** (top-level) holds real tooling that belongs in git, not
  hand-edited in place on oscar: `start_all_minecraft_servers.sh`,
  `stop_all_minecraft_servers.sh`, `scafold_new_minecraft_server.sh` +
  `scafold_help.txt`, `config_ufw_rules.sh`. (`minecraft_all_in_one_backup_v1.sh`
  is superseded in spirit by `minecraftmgr backup`, see
  [BAK.md](../epics/BAK.md) — kept for reference during migration, retired
  once `minecraftmgr backup run --all` is confirmed equivalent.
  `start_all_minecraft_servers.sh.old` and `sync.ffs_db` are cruft, not
  migrated.)
- **Not part of either split**: `.bash_history`, `.cache`, `.local` at the
  top level of `/srv/minecraft` suggest `$HOME` has pointed here at some
  point — don't carry that forward into the new `/srv/mc` checkout.
  `logs/` and `readme/` (top-level, distinct from each realm's own
  `logs/`) weren't inspected — triage those by hand during migration
  (move into the repo if they're real docs/notes, discard if not).

## Capacity (checked Aug 2026)

```
Filesystem      Size  Used Avail Use% Mounted on
/dev/nvme0n1p4  147G   45G   95G  33% /
/dev/nvme0n1p7  688G   29G  625G   5% /srv/minecraft
/dev/sdb1       5.5T  4.4T  841G  85% /mnt/backup
```

Realm data totals ~32GB (`cave_1_21_1` and `river_1_21_1` are the largest
at ~4.3-4.4G each), plus the ~807M jar cache — call it ~34GB to migrate.

**`/opt` is not its own filesystem — it lives on root** (`nvme0n1p4`).
`/srv/minecraft`'s disk (`nvme0n1p7`) is dedicated, 688G, and only 5%
used. Putting `/opt/mc` on root would mean world data — which only grows,
forever, via autosave — competes with the OS for space on a 147G disk
already a third full. That's backwards: the big dedicated disk should
back `/opt/mc`, and the small git checkout (source + docs, no data)
should live on root, where 95G is overkill anyway. **This changes the
runbook below** — see [Step 0](#0-repoint-optmc-at-the-spacious-disk).

**`/mnt/backup` is at 85% (841G free of 5.5T).** Real headroom, but not
huge relative to 4.4T already there. Don't retire the old backup script's
"keep last 3" retention (see [Step 4](#4-retire-the-old-backup-script))
until `minecraftmgr backup` has an equivalent — unbounded archive growth
on a disk that's already 85% full will bite fairly quickly.

**`gatorland_26_2/` is 4.0K — essentially empty.** Its directory
timestamp matches the same day as this discovery, same as the top-level
`/srv/minecraft` dir and `templates/`. That reads as a realm mid-setup
(no `world/`, no jar dropped in yet), not a normal migration target.
Confirm its actual state before running the per-realm steps below against
it — it may need to skip straight to being scaffolded fresh in the new
layout instead of migrated.

## Execution log (verified live, Aug 15-16 2026)

Step 0 and a full single-realm migration (`jitterbug_1_21_1`) were run for
real, end to end, including getting a player connected through a new
`jitterbug.gamenightbymike.com` subdomain. Several things below deviated
from the plan as originally written — this section is what actually
happened, and the sections after it are updated to match.

**The mount flip hit an extra blocker the plan didn't anticipate: a Samba
share.** `sudo umount /srv/minecraft` failed with "target is busy" even
after every realm was stopped. `sudo fuser -vm /srv/minecraft` (needs
`sudo` — a non-root `fuser` silently misses other users' open files)
showed `smbd` holding it open. `/etc/samba/smb.conf` has a `[Minecraft]`
share (`path = /srv/minecraft`, `force user = minecraft`) — almost
certainly the actual way day-to-day file edits happen on this box, not
git. Fix, run before the `umount`:

```bash
sudo sed -i 's#path = /srv/minecraft#path = /opt/mc#' /etc/samba/smb.conf
sudo systemctl restart smbd   # drops active connections, they reconnect transparently
sudo fuser -vm /srv/minecraft   # confirm empty now
```

**Editing live realm config now goes through this share, not SSH.** With
`path = /opt/mc` and `force user = minecraft`, the existing `\\oscar\Minecraft`
mapped drive is the easiest way to hand-edit a running realm's
`server.properties` or similar — edits land as the `minecraft` user
automatically, sidestepping the permission boundary below. (Config changes
still need a realm restart to take effect; Minecraft reads
`server.properties` at startup, not continuously.)

**`mike` cannot start or stop realms — only `minecraft` can.** This isn't
a permissions gap to fix, it's the intended boundary (see
[Out of scope](#out-of-scope)): the world's `session.lock` and other live
files are `-rw-r-----`, owned by `minecraft`, group `backup` **read-only**.
`mike` is in the `backup` group but that only grants read. Attempting
`./start.sh` as `mike` fails with
`java.nio.file.AccessDeniedException: ./world/session.lock`. Every
start/stop in this runbook must run as `minecraft`
(`sudo -iu minecraft`), not `mike`. `screen -list` is also per-user —
checking as the wrong user reliably looks like "nothing is running" even
when it is.

**A stale `latest.log` produced a red herring.** After a crashed start,
`logs/latest.log` doesn't get overwritten until Log4j initializes far
enough into startup — a crash before that point (like the permission
error above) leaves the *previous* run's log untouched. `jitterbug`'s
`latest.log` was over a year old (`Jul 6 2025`) and several real attempts
were misdiagnosed against it before checking `ls -la` on the file's mtime
exposed the problem. Always check the log's timestamp before trusting its
content as "this run."

**No Velocity proxy actually exists, so every realm needs its own
port-forward and DNS record — not the shared-port design the runbook
describes.** See the new [Connectivity](#connectivity-per-realm-dns-port-forward-firewall)
section below.

## Connectivity per realm: DNS, port-forward, firewall

[oscar-realm-hosting.md](oscar-realm-hosting.md) describes one shared
port-forward (`25565`) with Velocity routing every realm by hostname, and
reserves the "own port + `SRV` record" pattern for the modded-realm
exception. In reality, since Velocity was never deployed (see
[oscar-realm-hosting.md](oscar-realm-hosting.md)'s note), **every realm
needs the "exception" pattern** — there's no proxy to do hostname routing,
so each realm gets its own port, port-forward rule, and DNS record. Three
things to set up per realm, confirmed by getting `jitterbug` reachable
live:

**1. AT&T router port-forward** (`NAT/Gaming` page). The existing
`Minecraft_Arbor_1_21_1` entry was found forwarding port `26005` — which
is actually gravestone's port, not arbor's (the label went stale when the
rule was repurposed; forwarding is purely port-based, the label is just
text). Only one forward existed for all 9 realms, matching the manual
"forward whichever realm I'm using" workflow this migration is meant to
replace. Add a new entry per realm under "Application Hosting Entry" →
"Custom Services" if the realm isn't already in the service dropdown:
port = the realm's `port` from `servers.json`, protocol `TCP` (Minecraft
doesn't need UDP), device = `oscar`.

**2. Cloudflare DNS — `A` + `SRV`, not `CNAME`.** `mc.gamenightbymike.com`
(the base `A` record the runbook assumes already exists) didn't exist at
all — confirmed via `nslookup` returning `Non-existent domain`. Create it
once:
- Type `A`, Name `mc`, Content = oscar's current public IP (check with
  `curl -s https://api.ipify.org` from oscar), Proxy status **DNS only**
  (grey cloud — Cloudflare's proxy can't forward raw Minecraft TCP), TTL
  Auto.

Then per realm, an `SRV` record (Cloudflare's "Add record" UI combines
service+protocol+name into one field):
- Type `SRV`, Name `_minecraft._tcp.<realm>`, Priority `0`, Weight `5`,
  Port = the realm's port, Target `mc.gamenightbymike.com`.

This lets a client connect to `<realm>.gamenightbymike.com` with no port
typed, same end-user experience the runbook promises via Velocity, just
achieved per-realm instead of through a shared proxy.

Also worth checking before wiring up a new realm: the DDNS cron job
described in the runbook (`/opt/ddns/cloudflare-ddns.sh` keeping the `A`
record in sync with oscar's IP) may not actually be installed, given the
`A` record itself didn't exist. Confirm it's running before relying on it
— otherwise `mc.gamenightbymike.com` will silently go stale the next time
oscar's public IP changes.

**3. `ufw` needs an explicit allow rule per realm's port.** The router
forward being correct doesn't matter if oscar's own firewall drops the
packet first — and it will, by default. `sudo ufw status numbered` showed
existing rules only for ports `26005` and `26010` (both realms that
already had connectivity set up); nothing else. A ~20-second "Connecting
to the server..." timeout in the Minecraft client (not an instant
refusal) is the signature of this — the connection isn't being rejected,
it's being silently dropped before it reaches anything. Add the rule,
matching the existing comment style:

```bash
sudo ufw allow <port>/tcp comment 'Minecraft server port <port> (<realm>)'
```

No realm restart needed for a `ufw` change — it filters at the firewall
level before packets reach the process, so it takes effect immediately
for new connections.

**IPv6 is also a real, separate problem, independent of all of the
above.** Oscar's outbound IPv6 to the internet is broken —
`curl -6 https://api.minecraftservices.com/publickeys` fails outright
(`curl: (7)`), while `curl -4` to the same URL succeeds cleanly. DNS
returns IPv6 addresses first for Mojang's domains, and the JVM prefers
IPv6 when both are offered, so a plain `java -jar server.jar` silently
fails its Yggdrasil key fetch (`Failed to request yggdrasil public key`,
manifesting as a Gson parse error over what's actually a broken/WAF-like
response) — a failure that looks like a Mojang-side or network block but
is actually oscar's own IPv6 path. Fix: force IPv4 in every realm's
`start.sh`:

```bash
java -Djava.net.preferIPv4Stack=true -Xms$MEM_MIN -Xmx$MEM_MAX -jar "$JAR" nogui --port $PORT
```

This needs to be in the [`start.sh` template](#templating-startsh) below,
not just patched per-realm as issues come up.

## Velocity proxy deployment (live, Aug 16 2026)

The [Connectivity per realm](#connectivity-per-realm-dns-port-forward-firewall)
section above describes the fallback ("every realm gets its own port")
state that existed because Velocity had never actually been deployed.
That's no longer true for `gravestone` and `jitterbug` — the real
Velocity proxy described in
[oscar-realm-hosting.md](oscar-realm-hosting.md) Step 7 is now running on
oscar, and those two realms sit behind it on the single shared port
(`25565`). The other 7 realms still need the per-realm treatment until
they're brought onto the proxy too.

**Why now:** getting to "no port, no port-forward per realm" was the
whole point of the original design — the per-realm `SRV` pattern was
always meant to be temporary. This is that temporary state ending, one
realm pair at a time.

### Pre-existing blockers this surfaced

Standing up Velocity meant actually inspecting what the two realms were
running, which turned up two things the registry didn't reflect:

- **`jitterbug`'s jar was vanilla, not Paper**, despite `servers.json`
  saying `server_type: paper`. Its manifest's `Main-Class` was
  `net.minecraft.bundler.Main` (the stock Mojang server bootstrap) — the
  `paper` label was simply wrong. Vanilla has no support for any proxy
  forwarding scheme (legacy or modern), so this was a hard blocker for
  putting it behind Velocity at all, not just a labeling bug.
- **`gravestone` was genuinely Fabric**, running 3 mods (`fabric-api`,
  a custom `gravestones` mod, and its `pneumonocore` dependency). Fabric
  has no native Velocity forwarding support either — it needs an add-on
  mod like FabricProxy-Lite to speak the proxy protocol at all.

Rather than add a compatibility mod to gravestone, the decision was to
drop all three mods and convert both realms to Paper, which supports
Velocity's modern forwarding natively. This does mean gravestone lost
whatever gameplay the `gravestones` mod added — an explicit, deliberate
tradeoff, not a side effect.

### Converting both realms to Paper

> The steps below are the real, one-time execution log for these two
> specific realms. The same process, generalized into a repeatable runbook,
> lives at [convert-engine.md](../workflows/convert-engine.md) — use that
> for converting any other realm; keep reading here for the narrative and
> the gotchas actually hit doing it live.

Paper jars came from PaperMC's current Fill API
(`fill.papermc.io/v3/projects/...`) — the old `api.papermc.io/v2`
endpoint referenced in [oscar-realm-hosting.md](oscar-realm-hosting.md)
has since been sunset and returns an error. Exact builds used: Paper
`1.21.1` build 2 (jitterbug), Paper `26.1.2` build 53 (gravestone).

Process, run from the dev box over SSH plus the `minecraft` user for
anything touching the live process (see
[the minecraft-user playbook](#what-had-to-run-as-minecraft) below):

1. **Backed up gravestone first.** `world/level.dat` and `level.dat_old`
   are `-rw-------`, owned by `minecraft` — not even group-readable, so
   `mike` genuinely cannot read them, running or not. The safety `tar`
   had to run as `minecraft`, saved to
   `/mnt/backup/minecraft/gravestone_26_1_2_pre-paper-swap_<timestamp>.tar.gz`
   (~2.6GB). jitterbug didn't get one — explicitly disposable, per
   earlier sessions.
2. **Swapped jars in place**, same filename `start.sh` already expects
   (`server_<data_dir>.jar`), so no `start.sh` edits needed for this
   part. Old jars kept, not deleted:
   `server_jitterbug_1_21_1.jar.vanilla-bak`,
   `server_gravestone_26_1_2.jar.fabric-bak`.
3. **Moved gravestone's Fabric `mods/` and `config/` aside**
   (`mods.disabled-fabric/`, `config.disabled-fabric/`) rather than
   deleting — Paper ignores them either way, keeping them costs nothing
   and preserves the option to revert.
4. **First boot triggered Paper's standard one-time world migration**
   (nether/end folder restructuring for jitterbug's vanilla world;
   a "WorldFolderMigration" pass for gravestone with a 30-second
   "interrupt now if you don't have a backup" warning). Both completed
   cleanly, both worlds loaded intact — confirmed live by connecting and
   checking the world was gravestone's real one, not a fresh generation.
5. **Two unrelated data-pack warnings on gravestone's boot**
   (`Missing data pack fabric-convention-tags-v2`,
   `Missing data pack gravestones`) are expected and harmless — direct
   fallout of removing the mods, not something to fix.

### Java version gotchas (two, in opposite directions)

- **jitterbug's Paper build crashed on first boot** — a JVM `SIGSEGV`
  inside spark's bundled `libasyncProfiler.so`
  (`hs_err_pid<pid>.log` pinned it to
  `VMThread::nativeThreadId`/`Profiler::updateThreadName`). Oscar's
  default `java` is a very new build (Temurin 25.0.2, JRE version
  "25"), and this Paper build's bundled async-profiler wasn't tested
  against it. Gravestone's newer Paper build didn't hit this on the same
  Java 25, so it's specific to jitterbug's older build. **Fix**: pinned
  jitterbug's `start.sh` to explicitly invoke
  `/usr/lib/jvm/java-21-openjdk-amd64/bin/java` instead of the bare
  `java` on `$PATH`. Both Java 17 and 21 were already installed on
  oscar — no new install needed. Gravestone was left on the default
  Java 25 since it wasn't affected.
- **Velocity 4.0.0 itself requires Java 25**, the opposite problem —
  running it with the Java 21 binary fails outright with
  `UnsupportedClassVersionError` (class file version 69 vs. the JRE's
  max of 65). So oscar currently runs a genuinely mixed Java setup:
  Velocity on Java 25, gravestone on Java 25, jitterbug on Java 21. Not
  tidy, but each pinning is load-bearing — don't "simplify" this later
  without re-testing.

### Velocity config

Installed at `/opt/mc/_proxy` (Velocity 4.0.0, downloaded the same way
as the Paper jars, via the Fill API — the old install instructions in
[oscar-realm-hosting.md](oscar-realm-hosting.md) also predate the API
migration). `velocity.toml`:

```toml
bind = "0.0.0.0:25565"
player-info-forwarding-mode = "MODERN"
forwarding-secret-file = "forwarding.secret"

[servers]
jitterbug = "127.0.0.1:26887"
gravestone = "127.0.0.1:26005"
try = ["gravestone"]

[forced-hosts]
"jitterbug.gamenightbymike.com" = ["jitterbug"]
"gravestone.gamenightbymike.com" = ["gravestone"]
```

Both backends need matching trust configured in
`config/paper-global.yml` (generated by Paper on first boot, so this
config comes *after* the Paper conversion above, not before):

```yaml
proxies:
  velocity:
    enabled: true
    online-mode: true
    secret: '<contents of /opt/mc/_proxy/forwarding.secret>'
```

...and `server.properties` on both needs `online-mode=false` — Velocity
does the real Mojang handshake and forwards verified identity; a backend
that also tries its own Mojang auth on a proxied connection will reject
it.

**This is an atomic cutover, not a gradual one.** The moment a backend's
`paper-global.yml` has `proxies.velocity.enabled: true` and it restarts,
it stops accepting *any* direct connection — including from the LAN,
including from the old port-forward — regardless of whether Velocity
itself is even running yet. There's no window where both direct and
proxied access work side by side. Practical implication: don't flip a
realm's forwarding trust until Velocity is already confirmed running,
or you'll strand that realm with zero connectivity until it is.

### Network cutover

Once both realms trusted the proxy, the per-realm connectivity from
[Connectivity per realm](#connectivity-per-realm-dns-port-forward-firewall)
got replaced with the single-port design:

- **AT&T router**: one port-forward, `25565/TCP` → oscar. The old
  `26005`/`26887` entries were removed (they'd stopped working anyway —
  see the atomic-cutover note above).
- **`ufw`**: `25565/tcp` allowed (both v4 and v6 rules appeared —
  oscar's ufw config apparently duplicates rules per address family).
  The old `26005`/`26887` rules are now dead weight (harmless, but worth
  removing during a later cleanup pass).
- **Cloudflare**: the `mc.gamenightbymike.com` `A` record already
  existed from the earlier per-realm work and needed no changes. The
  per-realm `_minecraft._tcp.<realm>` `SRV` records got deleted and
  replaced with plain `CNAME`s: `gravestone` → `mc.gamenightbymike.com`,
  `jitterbug` → `mc.gamenightbymike.com` (both DNS-only / grey cloud,
  matching the `A` record).

### What had to run as `minecraft`

Everything that touches a live process or a `-rw-------` file still has
to run in the user's own `minecraft` shell (`sudo -iu minecraft`) — the
Claude Code SSH key only has `mike`, and `mike` can't `sudo`
non-interactively (see [[oscar_ssh_access]]). The full sequence used
tonight, reusable for the remaining realms:

```bash
# graceful stop (repeat per realm)
screen -S <realm> -p 0 -X stuff "say Restarting...$(printf '\r')"
sleep 2
screen -S <realm> -p 0 -X stuff "save-all$(printf '\r')"
sleep 2
screen -S <realm> -p 0 -X stuff "stop$(printf '\r')"
sleep 10
pgrep -af server_<realm>.jar   # must print nothing before continuing

# gravestone only: safety backup before any risky change
# (level.dat etc. are -rw------- minecraft-owned, mike can never read them)
tar czf /mnt/backup/minecraft/<realm>_<purpose>_$(date +%Y%m%d_%H%M%S).tar.gz \
  world server.properties eula.txt ops.json whitelist.json \
  banned-ips.json banned-players.json usercache.json mods/ config/

# start the proxy (once, not per-realm)
cd /opt/mc/_proxy
screen -dmS velocity_proxy java -jar velocity.jar

# start each realm
cd /opt/mc/<realm> && screen -dmS <realm> ./start.sh
```

**The graceful `stop` command doesn't always take effect** — jitterbug's
old vanilla process ignored it once, and the only reliable follow-up was
`ps aux | grep server_<realm>.jar` to get the PID and `kill` it directly
(`kill -9` if plain `kill` doesn't clear it after a few seconds). Always
verify the process is actually gone (`pgrep`) before starting a
replacement — starting a second instance while the first is still alive
produces a `session.lock` `AccessDeniedException`/`LockException`, not a
helpful "already running" message.

**Don't run start commands from the automation SSH key.** The key only
has `mike`, and a realm started as `mike` races against the same realm
started correctly as `minecraft` — both bind the same port and lock file
simultaneously, and whichever loses becomes a zombie that has to be
killed by PID. Every start/stop goes through the user's own `minecraft`
shell, no exceptions, even under time pressure.

**Log rotation can hide the process you actually care about.** Paper
rotates the *previous* run's full log into a numbered
`logs/<date>-<n>.log.gz` archive at the moment a *new* process claims
`logs/latest.log` — so if a duplicate/crashed start attempt happens
after a real successful boot, `latest.log` shows only the tiny crash,
and the real boot's log is one of the just-created `.gz` archives, not
`latest.log`. Check archive timestamps against `ps aux` start times
before concluding a boot failed.

### Verification status

Confirmed live: connecting to `192.168.1.113:25565` from inside the LAN
serves Velocity's MOTD (proof the proxy itself is up and reachable) and
the default `try` server (`gravestone`) loads the real, existing
gravestone world under the player's real Mojang identity — proof modern
forwarding actually works end-to-end, not just an offline-mode
passthrough.

**Not yet confirmed**: `jitterbug`'s forced-host routing (needs the
actual hostname sent by the client, which a raw-IP LAN test can't
exercise), and true external reachability for either realm. Both need a
test from a device off the home LAN (phone on cellular) — home routers
typically can't hairpin a LAN client back to the router's own public IP,
so `<realm>.gamenightbymike.com` won't resolve usefully from inside the
house even with DNS correct. Paused here pending that test.

## Realm-picker site + AUTOSTART trigger (Aug 16 2026)

Alongside the connectivity work, a static realm-picker page
(`minecraftmgr web build` → `public/index.html`, PR #19, issue #18) lists
every realm from `servers.json` with its version, status, and connect
address, meant for Cloudflare Pages — no router or oscar change needed
for the page itself.

Mid-build, the scope grew: an AUTOSTART button per non-running realm (PR
for issue #20). That button needs something on oscar that can actually
*start a process*, which is a different risk profile than a read-only
page, so it got its own explicit design decisions:

- **Reachability**: Cloudflare Tunnel (`cloudflared`), not a
  port-forward. `cloudflared` makes an *outbound* connection from oscar
  to Cloudflare's edge and gets a public hostname in return — no port
  ever opens on the router, consistent with the rest of this migration.
- **Access control**: one shared family PIN, sent as a request header,
  checked with a constant-time comparison
  (`hmac.compare_digest`) against a secret file on oscar — not
  Cloudflare Access, since that would mean everyone needs a Google/email
  login just to start a realm.
- **Who's allowed to actually start a realm**: the daemon that runs
  `screen -dmS <data_dir> ./start.sh` must run as the systemd
  `User=minecraft`. This is the same hard rule the Velocity cutover
  established the hard way (see "What had to run as `minecraft`" above)
  — it now applies to a long-running service, not just interactive
  commands, so it's enforced via the systemd unit's `User=` line instead
  of "remember to switch shells."

### What the code does

- `src/minecraftmgr/services/trigger_service.py` — pure logic, no
  network: `realm_running(data_dir)` greps `screen -ls` for a session
  matching the realm's data dir; `start_realm(server, data_root)` refuses
  to start a realm that's already running (avoids the duplicate-process
  race hit during the Velocity cutover) and otherwise runs
  `screen -dmS <data_dir> ./start.sh` with `cwd` set to the realm's data
  directory; `verify_pin` does the constant-time PIN check.
- `src/minecraftmgr/services/trigger_daemon.py` — a stdlib
  `ThreadingHTTPServer` (no new dependency) exposing `GET /status`
  (per-realm running/stopped) and `POST /start/<realm_id>` (PIN required
  via the `X-Autostart-Pin` header), with CORS headers so the
  Pages-hosted picker page can call it from a different origin.
- `minecraftmgr trigger serve` — CLI entry point, refuses to start if the
  PIN file doesn't exist yet rather than running with no access control.
- The picker page's JS calls `GET /status` on load; realms that come
  back `"stopped"` get an AUTOSTART button, realms that error out (no
  daemon reachable yet, or a network hiccup) just don't show one — the
  page stays fully usable as a plain address list either way.

### Deployed (Aug 16 2026)

The plan above assumed a clean slate; reality had two surprises worth
recording.

**`cloudflared` was already installed and authenticated** — an existing
tunnel (`mission-impossible`) was already live on this same domain,
routing `gamenightbymike.com` and `mi.gamenightbymike.com` to some other
app on `localhost:3000`, via a root-owned `/etc/cloudflared/config.yml`
and systemd's `cloudflared.service`. Deliberately left untouched rather
than adding an ingress rule to it — that would have meant restarting a
service actively serving something unrelated, for a few seconds of
downtime, to save creating one extra tunnel. Went with a second,
independent tunnel (`mc-trigger`) instead, config kept under `mike`'s own
home dir (`~/.cloudflared/mc-trigger-config.yml`, no root needed) rather
than `/etc/cloudflared/`, specifically so it can never collide with the
existing tunnel's config file.

**`minecraftmgr` has no console-script entry point** — `pyproject.toml`
never defined `[project.scripts]`, so the bare `minecraftmgr` command
doesn't exist; every invocation this whole project has ever used is
`python -m minecraftmgr`. The original runbook draft's
`ExecStart=/usr/bin/minecraftmgr ...` would have failed immediately.
Fixed by pointing `ExecStart` at the venv's `python -m minecraftmgr`
directly rather than blocking deployment on a packaging fix.

Actual steps, as run:

1. **`cloudflared` login**: skipped — already authenticated as `mike`
   from prior unrelated setup (`~/.cloudflared/cert.pem` already
   present).
2. **Create the tunnel and route DNS**, as `mike`, no `sudo`:
   ```bash
   cloudflared tunnel create mc-trigger
   cloudflared tunnel route dns mc-trigger trigger.gamenightbymike.com
   ```
3. **Config**, as `mike`, in `~/.cloudflared/mc-trigger-config.yml`
   (not `/etc/cloudflared/` — avoids touching the existing tunnel):
   ```yaml
   tunnel: 0cf98b0b-51a4-4db5-bf9f-4480e618d45d
   credentials-file: /home/mike/.cloudflared/0cf98b0b-51a4-4db5-bf9f-4480e618d45d.json
   ingress:
     - hostname: trigger.gamenightbymike.com
       service: http://127.0.0.1:8787
     - service: http_status:404
   ```
4. **Sync and install the package on oscar** — `/srv/mc` was 14 commits
   behind `main` and on a long-dead feature branch, and had never had
   `pip install -e .` run:
   ```bash
   cd /srv/mc
   git checkout main
   git pull
   .venv/bin/pip install -e .
   ```
5. **PIN file, as `minecraft`** (same permission boundary as
   `forwarding.secret` — owner-only, no group access):
   ```bash
   mkdir -p /opt/mc/_trigger
   printf '%s' '<the real pin>' > /opt/mc/_trigger/pin.secret
   chmod 600 /opt/mc/_trigger/pin.secret
   ```
6. **systemd units**, as `mike` with `sudo` — `mc-trigger.service` runs
   as `User=minecraft` (it's the one that actually starts realm
   processes); the tunnel service runs as `User=mike` (it only proxies
   HTTP to localhost, no realm-file access needed, and `mike` already
   owns the tunnel credentials from step 2-3):
   ```ini
   # /etc/systemd/system/mc-trigger.service
   [Unit]
   Description=MinecraftMgr realm start/status trigger daemon
   After=network.target

   [Service]
   User=minecraft
   WorkingDirectory=/srv/mc
   ExecStart=/srv/mc/.venv/bin/python -m minecraftmgr trigger serve
   Restart=on-failure
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```
   ```ini
   # /etc/systemd/system/cloudflared-mc-trigger.service
   [Unit]
   Description=Cloudflare Tunnel - MinecraftMgr trigger daemon
   After=network-online.target
   Wants=network-online.target

   [Service]
   User=mike
   TimeoutStartSec=15
   Type=notify
   ExecStart=/usr/bin/cloudflared --no-autoupdate --config /home/mike/.cloudflared/mc-trigger-config.yml tunnel run
   Restart=on-failure
   RestartSec=5s

   [Install]
   WantedBy=multi-user.target
   ```
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now mc-trigger.service cloudflared-mc-trigger.service
   ```

`mc-trigger.service` flapped through 15 restarts with `status=203/EXEC`
(systemd couldn't exec the venv's `python`) before settling — timing
lines up with `pip install -e .` from step 4 still reinstalling the venv
concurrently on the same box, not a real config problem. Stable since,
no repeat.

### Verification status

**Confirmed live**, over the real public URL (not just localhost):
`curl https://trigger.gamenightbymike.com/status` returns real `screen`
state for both realms; a wrong PIN on `/start/<realm>` gets a `403` and
starts nothing; an `OPTIONS` preflight against `/start/<realm>` returns
the correct CORS headers for a cross-origin fetch.

**Not yet confirmed**: the AUTOSTART button clicked from an actual
browser on the deployed picker page — curl can exercise the preflight
response but not a real button-click-to-fetch flow, and the picker page
itself isn't on Cloudflare Pages yet (still just the local mockup/build
output).

## Target layout

```
/srv/mc/                      <- git checkout of devmukmuk/MinecraftMgr
  src/, tools/, docs/, servers.json, minecraftmgr.yaml (untracked, oscar-local)

/opt/mc/
  _jarcache/                  <- shared jar cache (was templates/)
    server_1_21_10.jar ...
  gravestone_26_1_2/          <- data_dir from servers.json, one per realm
    world/, mods/, config/, .fabric/, libraries/, versions/,
    logs/, crash-reports/,
    server_gravestone_26_1_2.jar,
    server.properties, eula.txt, ops.json, whitelist.json,
    banned-ips.json, banned-players.json, usercache.json,
    log4j2.xml, start.sh

/mnt/backup/minecraft/        <- unchanged, becomes backups_root
```

## Per-realm file split

| Item | Destination | Why |
|---|---|---|
| `world/`, `mods/`, `.fabric/`, `libraries/`, `versions/`, `logs/`, `crash-reports/` | `/opt/mc/<data_dir>/` | binary/large/high-churn |
| `server_<name>.jar` | `/opt/mc/<data_dir>/` | binary, redownloadable via `jar_source` |
| `ops.json`, `whitelist.json`, `banned-ips.json`, `banned-players.json`, `usercache.json` | `/opt/mc/<data_dir>/` | mutated by the running server itself — git-tracking these would dirty the tree on every admin command |
| `server.properties`, `eula.txt` | `/opt/mc/<data_dir>/` | may be rewritten by the server on boot; the fields that matter (`port`, `minecraft_version`) already live in `servers.json` |
| `config/` (mod config) | `/opt/mc/<data_dir>/` | coupled to `mods/`, which is also untracked |
| `start.sh` | generated at `/opt/mc/<data_dir>/start.sh` | see [templating start.sh](#templating-startsh) below — the *template* lives in git, the *rendered* copy lives with the live realm since `screen` execs it directly from there |
| `log4j2.xml` | copied to `/opt/mc/<data_dir>/` from a shared git template | identical across realms today; one tracked template instead of 9 duplicated copies |

## Templating start.sh

`start.sh` is fully parametric already:

```bash
NAME="gravestone_26_1_2"   # == data_dir
PORT=26005                  # == servers.json port
MEM_MIN="6G"                 # not currently modeled in ServerEntry
MEM_MAX="8G"                 # not currently modeled in ServerEntry
JAR="server_${NAME}.jar"
```

`tools/templates/start.sh.template` (new, git-tracked) replaces `NAME` and
`PORT` with `data_dir`/`port` from `servers.json`. `MEM_MIN`/`MEM_MAX`
aren't in `ServerEntry` yet — until the schema grows those fields, keep
them as manually-set values in the rendered `/opt/mc/<data_dir>/start.sh`
(don't regenerate over hand-tuned memory settings without a real field to
drive it — see [Out of scope](#out-of-scope)).

**`minecraftmgr realm validate <id>|--all [--fix]`** (2026-08-18, see
[PROV-design.md](../epics/PROV-design.md#realm-validate-2026-08-18)) is the
tool this section anticipated but never built: it checks a realm's
`start.sh` against this exact template (the IPv4 flag, the port) and
`--fix` regenerates it, preserving whatever `MEM_MIN`/`MEM_MAX` the file
already has rather than guessing — same "don't regenerate over hand-tuned
memory settings" rule as above, just automated for everything except the
memory values themselves. Found live via real use: `arbor_1_21_10`,
`cave_1_21_1`, `poop_1_21_1`, and `river_1_21_1` all had `MEM_MAX="14G"`
(oscar only has 15Gi total) and none had the IPv4 flag — see
[DEP.md](../epics/DEP.md)'s open work.

The template's `java` invocation also needs
`-Djava.net.preferIPv4Stack=true` (confirmed necessary live — see
[Execution log](#execution-log-verified-live-aug-15-16-2026)):

```bash
java -Djava.net.preferIPv4Stack=true -Xms$MEM_MIN -Xmx$MEM_MAX -jar "$JAR" nogui --port $PORT
```

## Execution runbook

### 0. Repoint `/opt/mc` at the spacious disk

Since `nvme0n1p7` already holds every realm's data and has 625G free,
repoint its *mountpoint* from `/srv/minecraft` to `/opt/mc` instead of
copying ~34GB of world data across filesystems. This makes the migration
mostly free (metadata only) rather than an hours-long `rsync`:

```bash
# stop every realm first
/srv/minecraft/Scripts/stop_all_minecraft_servers.sh
# (that script's array is stale -- confirm with `screen -list` that
#  nothing is still running before continuing)

sudo umount /srv/minecraft

# edit /etc/fstab: change the nvme0n1p7 line's mountpoint from
# /srv/minecraft to /opt/mc -- verify only that one line changed
sudo sed -i 's#/srv/minecraft#/opt/mc#' /etc/fstab

sudo mkdir -p /opt/mc
sudo mount /opt/mc

df -h /opt/mc   # expect ~688G size, ~29G used, matching the old /srv/minecraft numbers
```

`/opt/mc` now directly contains what used to be at `/srv/minecraft`: all
9 realm folders (already correctly named — folder name == `data_dir`),
`templates/`, `Scripts/`, and the leftover cruft. Nothing needs to be
copied for the realms themselves.

The git checkout is small (source + docs, no data) and fits comfortably
on root:

```bash
sudo mkdir -p /srv/mc
sudo chown mike:mike /srv/mc
cd /srv/mc
git clone https://github.com/devmukmuk/MinecraftMgr.git .
tools/git-hooks/install.sh

# oscar-local config, never committed
cat > minecraftmgr.yaml <<'EOF'
paths:
  data_root: /opt/mc
  backups_root: /mnt/backup/minecraft
EOF

python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m minecraftmgr about   # sanity check
```

This checkout was cloned over plain HTTPS with no stored credentials —
fine for `git pull`, but it means **oscar cannot `git push`**
(confirmed: `remote: Permission ... denied`, `403`). Anything that
mutates `servers.json` on oscar (like Step 2's `server add` below) has to
get committed from a checkout that *can* push — either give oscar real
push credentials (a fine-grained PAT or deploy key) or treat "run
registry-mutating commands only from the dev box, oscar is pull-only" as
the actual rule. Not resolved yet — see [DEP.md](../epics/DEP.md)'s open
work.

### 1. Rename the shared jar cache

Same filesystem now, so this is an instant rename, not a copy:

```bash
mv /opt/mc/templates /opt/mc/_jarcache
```

### 2. Register each realm (repeat per realm)

No data movement needed — each realm's files are already sitting at the
right path (`/opt/mc/<data_dir>/`) after the remount. Registration runs
as `mike` (`/srv/mc` is `mike`-owned); starting the realm must run as
`minecraft` (see [Execution log](#execution-log-verified-live-aug-15-16-2026)
— `mike` gets `AccessDeniedException` on the world's lock file):

```bash
REALM=gravestone_26_1_2   # = data_dir; set per realm

cd /srv/mc
.venv/bin/python -m minecraftmgr server add "$REALM" \
  --name "Gravestone" \
  --port 26005 \
  --mc-version "26.1.2" \
  --type paper \
  --data-dir "$REALM"

# commit + push from a checkout that can actually push (see Step 0's note)

sudo -iu minecraft
cd "/opt/mc/${REALM}"
screen -dmS "$REALM" ./start.sh
exit
```

Add the template's `-Djava.net.preferIPv4Stack=true` flag to this realm's
`start.sh` before starting it if it hasn't been added yet (see
[Templating start.sh](#templating-startsh)) — otherwise Mojang session
verification will fail even though the server itself is fine.

**Then wire up connectivity** — port-forward, `SRV` record, `ufw` rule —
per [Connectivity per realm](#connectivity-per-realm-dns-port-forward-firewall)
above. None of that is optional per realm; skipping any one of the three
produces a working-looking server that's unreachable from outside oscar's
LAN (or, for the `ufw` step specifically, a client that hangs on
"Connecting to the server..." for ~20 seconds before failing).

Repeat for the 8 populated realms — **skip `gatorland_26_2` for now** (see
[Capacity](#capacity-checked-aug-2026), it's essentially empty and likely
mid-setup; confirm its real state before registering it as a normal
migrated realm). Set `status` on the 5 that were group-restricted
(`cave_1_20_4`, `cave_1_21_1`, `poop_1_21_1`, `poop_1_21_3`, `river_1_21_1`)
to `inactive` via `minecraftmgr server update <id> --status inactive` —
**confirm which are actually retired vs. just currently stopped** before
setting that; the permission bits are a signal, not a guarantee.

**This never actually happened** — as of 2026-08-18, `cave` (`cave_1_21_1`),
`poop` (`poop_1_21_1`), and `river` (`river_1_21_1`) are all registered
`active`, not `inactive` as this section recommended. Whether that's a
deliberate reversal or this step was simply skipped isn't confirmed. Worth
noting: these are exactly 3 of the 4 realms found live with the broken
`-Xmx14G`/missing-IPv4-flag `start.sh` (see the note above and
[DEP.md](../epics/DEP.md)'s open work) — plausible they were never really
production-ready and got left `active` by oversight rather than intent.

### 3. Port the scripts

**Done, as an import (2026-08-18)** — every currently-relevant script found
on oscar was copied verbatim into [tools/scripts/](../../tools/scripts/README.md),
with a provenance header noting its original path but no logic changes:
`start_all_minecraft_servers.sh`, `stop_all_minecraft_servers.sh`,
`config_ufw_rules.sh`, `minecraft_all_in_one_backup_v1.sh`,
`minecraft_single_backup.sh` (a newer variant found in `/opt/scripts/` that
wasn't known about when this section was first written), and
`extract-user-data.py` (deduplicated from three identical per-realm copies).
`scafold_new_minecraft_server.sh` + `scafold_help.txt` were kept too, for
reference, despite being superseded (see below) — `.old` files, `sync.ffs_db`,
and stale/duplicate copies were left behind; the full list of what was and
wasn't imported, and why, is in
[tools/scripts/README.md](../../tools/scripts/README.md).

**Not done yet**: none of the rewrites originally planned for this step
happened — `start_all`/`stop_all` still have the hardcoded `servers=(...)`
array instead of looping over `minecraftmgr server list --active-only`,
and the two backup scripts haven't been consolidated. Those are tracked as
the "known issues" column in `tools/scripts/README.md`, to be picked off
incrementally rather than rewritten all at once.

Getting oscar to actually run these tracked copies instead of the untracked
originals at `/opt/mc/Scripts/` and `/opt/scripts/` is a separate manual
cutover — see
[docs/workflows/redeploy-oscar-scripts.md](../workflows/redeploy-oscar-scripts.md).
That includes deleting `/opt/mc/Scripts/` once the new location is confirmed
working, same as this section originally said.

`scafold_new_minecraft_server.sh` specifically is superseded by
[PROV](../epics/PROV-design.md)'s `minecraftmgr realm provision`/`activate`
rather than being revived — imported for reference only, not meant to be
redeployed or run again.

### 4. Retire the old backup script

Once `minecraftmgr backup run --all` (pointed at the new
`backups_root: /mnt/backup/minecraft`) has been verified to produce
usable archives for a couple of realms, stop cron'ing
`minecraft_all_in_one_backup_v1.sh`. Its stop/backup/restart-if-was-running
behavior and 3-backup retention aren't in `minecraftmgr backup` yet — see
[BAK.md](../epics/BAK.md)'s open work — don't retire it until those gaps
are either accepted or closed.

### 5. Verify, then clean up

- Confirm each migrated realm is reachable and its world loaded correctly
  (not a fresh world — the surest sign a `data_dir` was wrong).
- Confirm `minecraftmgr backup run --all` produces one archive + `.sha256`
  per active realm under `/mnt/backup/minecraft`.
- Only after both are confirmed for every realm: `/opt/mc/Scripts/` can go
  (once [Step 3](#3-port-the-scripts) is confirmed working from
  `/srv/mc/tools/scripts/`). Triage what's left by hand —
  `/opt/mc/logs/` and `/opt/mc/readme/` (top-level, distinct from each
  realm's own `logs/`) get moved into the repo if they're real docs/notes
  and discarded otherwise; `.bash_history`, `.cache`, `.local` are shell
  artifacts from `$HOME` having pointed here at some point and can be
  removed; `lost+found` is a normal ext4 artifact of the filesystem and
  can stay. There's no separate "old" directory to decommission — the
  remount in Step 0 means `/opt/mc` *is* the same disk that used to be
  `/srv/minecraft`, just relabeled.

## Out of scope (for this migration)

- **Converting `screen` to systemd units.** The runbook in
  [oscar-realm-hosting.md](oscar-realm-hosting.md) describes systemd, but
  that was never deployed — this migration preserves the real `screen`
  mechanism as-is. Worth its own epic later; folding it into this
  migration would couple two independently risky changes together.
- **`ServerEntry` gaining `mem_min`/`mem_max` fields** so `start.sh` can be
  fully generated instead of partially hand-set. Small schema change, but
  a separate [REG](../epics/REG.md) decision, not required for the split
  itself.
- **Backup retention/pruning** in `minecraftmgr backup` (matching the old
  script's "keep last 3"). Tracked as [BAK](../epics/BAK.md) open work.
