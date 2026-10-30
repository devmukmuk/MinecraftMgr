# Hardcore realm: set it up, and Archive & Reset between runs

**Automation status:** Set-up is the normal provisioning path plus `--mode
hardcore`. Archive & Reset is fully automated: one button on the realm page,
behind the family PIN.

A hardcore realm has `"mode": "hardcore"` in `servers.json` and
`hardcore=true` (plus `difficulty=hard`) in its `server.properties`. Each
player gets one life. A **run** is one world, from the first join until the
last player dies. On the page at minecraft.gamenightbymike.com, hardcore
realms:

- are listed first, with a red border and a **Hardcore · one life** badge
- have **Autostart**, like every other realm
- have **This run & past runs** (family PIN): who played, play time, order
  of deaths, last player alive, and one line for each archived run
- have **Archive & Reset** (family PIN plus a seed for the next world; blank
  means random), which works only once every player in the run has died

## Set up `hardcore` (one time)

Registered in `servers.json` as `hardcore`, port `26666`, Minecraft 26.3
(Paper build 231), data_dir `hardcore`. Provisioned 2026-10-30.

1. **Deploy this code to oscar** and restart `mc-trigger.service`. As
   `mike` (the checkout at `/srv/mc` is `mike`-owned; the service itself runs
   as `minecraft`):
   ```bash
   cd /srv/mc
   git checkout main
   git pull
   sudo systemctl restart mc-trigger.service
   sudo systemctl status mc-trigger.service --no-pager
   ```
   The new `/hardcore` and `/reset/<id>` endpoints don't exist until the
   service restarts.
2. **Check that port 26666 is free on oscar.** `servers.json` doesn't list
   every port in use there:
   ```bash
   ss -ltn | grep 26666
   ```
3. **Cache the Paper jar** if `_jarcache` doesn't have this version yet.
   Provision fails fast with `server_26_3.jar not found` if it's missing. See
   [PAPER.md](../PAPER.md) for finding the build's URL and sha256. As `mike`:
   ```bash
   cd /tmp
   curl -L -o server_26_3.jar "<download url>"
   echo "<sha256>  server_26_3.jar" | sha256sum -c - \
     && sudo install -o minecraft -g minecraft -m 644 server_26_3.jar /opt/mc/_jarcache/server_26_3.jar
   ```
4. **Provision.** Run it from `mike`'s shell, as `minecraft`, because it
   does a first boot:
   ```bash
   cd /srv/mc
   sudo -u minecraft /srv/mc/.venv/bin/python -m minecraftmgr realm provision hardcore \
     --name "Hardcore" --port 26666 --mc-version 26.3 --mode hardcore
   ```
   Skip the `server add` line in the handoff output, because the realm is
   already registered. Do the Velocity and Cloudflare steps it prints:
   [modify-cloudflare-cname.md](modify-cloudflare-cname.md) for
   `hardcore` → `mc.gamenightbymike.com`.
5. **Check that Velocity supports the realm's version.** If players get
   `Incompatible client! Please use 1.7.2-<version>`, the proxy is older than
   the realm. That happened with 26.3 on Velocity 4.0.0. See
   [upgrade-velocity.md](upgrade-velocity.md).
6. **Whitelist the players**, as described in
   [modify-whitelist.md](modify-whitelist.md).

To turn an existing realm into a hardcore one, run `server update <id> --mode
hardcore` on the dev box, then set `hardcore=true` and `difficulty=hard` in
its `server.properties` on oscar. Hardcore only applies to a newly created
world, so the realm needs an Archive & Reset (or a new world) afterwards.

## What Archive & Reset does

`POST /reset/<id>` on the trigger daemon
(`hardcore_service.archive_and_reset`):

1. Refuses unless the realm is `hardcore`, someone has played this run, and
   **every** player in the run has died. The page shows the reason, for
   example `Still alive: Cal`.
2. Stops the realm if it's running (dead players stay connected as spectators).
3. Writes `world/`, `world_nether/`, `world_the_end/`, `logs/` and
   `server.properties` to
   `<backups_root>/hardcore/<id>/<id>-run<N>-<timestamp>.tar.gz` (on oscar,
   `/mnt/backup/minecraft/hardcore/hardcore/`) with a `.sha256` file, and reads
   the archive back before deleting anything.
4. Appends the run summary to `hardcore_runs.json` in the realm folder.
   This file is the history the page shows.
5. Deletes the world folders and `logs/`. The jar, `start.sh`, configs,
   plugins, whitelist, ops and `usercache.json` are kept.
6. Sets `level-seed` to the seed that was entered (blank means random).

The next Autostart creates a new world.

**Where the summary comes from:** play time and a death count come from
`world/stats/<uuid>.json`, with names taken from `usercache.json`. The order
of deaths comes from the timestamped death messages in `logs/`. A line counts
as a death when it's a known player's name followed by a vanilla death
message ("was slain by", "fell from", "drowned", ...). If a death shows in
the stats but its message can't be found, that player still counts as dead
and is listed after the ordered deaths. Each reset clears `logs/`, so each
run's summary only covers that run.

## Verify

- After a reset: `ls /mnt/backup/minecraft/hardcore/hardcore/` shows the new
  `.tar.gz` and `.sha256`, `hardcore_runs.json` has one more entry, and
  `grep level-seed /opt/mc/hardcore/server.properties` shows the seed.
- After the next Autostart, a player who joins spawns in a new world, and
  **This run & past runs** shows the fresh run plus the archived one.

## Restore an archived run

Stop the realm, move the current `world*` folders aside, and extract the
run's archive into `/opt/mc/hardcore/`, as described in
[restore-from-backup.md](restore-from-backup.md). The archive's
`server.properties` keeps that run's seed.
