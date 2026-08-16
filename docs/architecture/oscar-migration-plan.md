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

## Execution runbook

Run once, on oscar. `df -h /opt /srv/minecraft /mnt/backup` first — some
realm `world/` dirs plus the ~800MB jar cache need to fit on whatever
filesystem backs `/opt`, and if `/opt` is a different filesystem than
`/srv/minecraft`, the moves below are real copies (via `rsync`, not a bare
`mv`) that need headroom for both copies to exist briefly.

### 0. One-time setup

```bash
sudo mkdir -p /opt/mc/_jarcache
sudo mkdir -p /srv/mc
cd /srv/mc
git clone https://github.com/devmukmuk/MinecraftMgr.git .
tools/git-hooks/install.sh

# oscar-local config, never committed
cat > minecraftmgr.yaml <<'EOF'
paths:
  data_root: /opt/mc
  backups_root: /mnt/backup/minecraft
EOF
```

### 1. Move the shared jar cache

```bash
rsync -a --info=progress2 /srv/minecraft/templates/ /opt/mc/_jarcache/
# verify, then:
rm -rf /srv/minecraft/templates
```

### 2. Migrate each realm (repeat per realm)

```bash
REALM=gravestone_26_1_2   # = data_dir; set per realm

# stop it first so world/ isn't moved out from under a live process
screen -S "$REALM" -X stuff "save-all
stop
"
sleep 10   # confirm with: screen -list | grep "\.${REALM}"

sudo mkdir -p "/opt/mc/${REALM}"

rsync -a --info=progress2 "/srv/minecraft/${REALM}/" "/opt/mc/${REALM}/"
# verify counts/sizes match, then:
rm -rf "/srv/minecraft/${REALM}"

# render start.sh from the template (fills in NAME/PORT; MEM_MIN/MEM_MAX
# carried over by hand from the original start.sh for this realm)
# ...then register it in the registry:
cd /srv/mc
python -m minecraftmgr server add "$REALM" \
  --name "Gravestone" \
  --port 26005 \
  --mc-version "26.1.2" \
  --type paper \
  --data-dir "$REALM"

# restart from the new location
cd "/opt/mc/${REALM}"
screen -dmS "$REALM" ./start.sh
```

Repeat for all 9 realms. Set `status` on the 5 that were group-restricted
(`cave_1_20_4`, `cave_1_21_1`, `poop_1_21_1`, `poop_1_21_3`, `river_1_21_1`)
to `inactive` via `minecraftmgr server update <id> --status inactive` —
**confirm which are actually retired vs. just currently stopped** before
setting that; the permission bits are a signal, not a guarantee.

### 3. Port the scripts

Copy the four still-relevant scripts into `tools/scripts/` in the repo
(drop `.old` files, `sync.ffs_db`, and the backup script — see below),
commit via the normal issue/branch/PR flow, then on oscar replace the
`/srv/minecraft/Scripts/` copies with symlinks (or just delete them once
`/srv/mc/tools/scripts/` is confirmed working) so there's one copy of the
truth, reviewed via PR going forward:

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

### 5. Verify, then decommission

- Confirm each migrated realm is reachable and its world loaded correctly
  (not a fresh world — the surest sign a `data_dir` was wrong).
- Confirm `minecraftmgr backup run --all` produces one archive + `.sha256`
  per active realm under `/mnt/backup/minecraft`.
- Only after both are confirmed for every realm: nothing should remain
  under `/srv/minecraft` except the untriaged `logs/`/`readme/` and the
  shell-history cruft. Rename it (`mv /srv/minecraft /srv/minecraft.pre-migration`)
  rather than deleting outright, and keep it for a confirmed window before
  removing it for good.

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
