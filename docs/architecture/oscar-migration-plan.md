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

### 3. Port the scripts

Copy the four still-relevant scripts into `tools/scripts/` in the repo
(drop `.old` files, `sync.ffs_db`, and the backup script — see below),
commit via the normal issue/branch/PR flow, then on oscar delete
`/opt/mc/Scripts/` once `/srv/mc/tools/scripts/` is confirmed working so
there's one copy of the truth, reviewed via PR going forward:

- `start_all_minecraft_servers.sh`, `stop_all_minecraft_servers.sh` —
  update to loop over `minecraftmgr server list --active-only` instead of
  the hardcoded `servers=(...)` array
- `scafold_new_minecraft_server.sh` + `scafold_help.txt`
- `config_ufw_rules.sh`

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
