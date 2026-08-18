# Stop / restart a realm

**Automation status:** Full — one command each, as of 2026-08-18.
`minecraftmgr realm start <id>`/`--all` and `realm stop <id>`/`--all` wrap
`trigger_service.start_realm()`/`stop_realm()` (the same logic the
realm-picker page's AUTOSTART button already used for a single realm, and
that `provision`/`activate`'s first-boot cycle already used internally).
`realm status [id]` reports live `screen` state (running/not, for one realm
or every registered one), reading the same `realm_running()` check the
AUTOSTART button's `GET /status` endpoint uses. Not yet redeployed to oscar
as the actual replacement for
`start_all_minecraft_servers.sh`/`stop_all_minecraft_servers.sh` — see
[redeploy-oscar-scripts.md](redeploy-oscar-scripts.md) and
[tools/scripts/README.md](../../tools/scripts/README.md).

## Capacity cap (2026-08-18)

`realm start` (single id, `--all`, and the AUTOSTART button) refuses to
exceed `Settings.max_running_servers` (default 3 — oscar only has 15Gi RAM,
see [PROV-design.md](../epics/PROV-design.md#realm-validate-2026-08-18)'s
`-Xmx14G` incident). At capacity, it looks for a currently-running realm
with nobody connected and stops that one to make room; if every running
realm has someone connected, the start is refused with a "N realms already
running, none idle — try again shortly" message rather than exceeding the
cap or silently doing nothing. This is reactive, not scheduled — nothing
ever gets stopped just for being idle; only a blocked start triggers an
eviction. See [PROV-design.md](../epics/PROV-design.md#capacity-cap-and-on-demand-idle-eviction-2026-08-18)
for the full design.

## When to use

Any workflow that says "stop the realm first" — [change-port](change-port.md),
[update-jar-version](update-jar-version.md), editing `server.properties`
directly. Also useful on its own to free up memory on oscar for a realm
nobody's using, without deregistering it.

## Steps

As the `minecraft` user on oscar — **only `minecraft` may do this**, never
the `mike` automation key:

```bash
sudo -iu minecraft
cd /srv/mc
python -m minecraftmgr realm stop <id>
# or, for every active realm:
python -m minecraftmgr realm stop --all
```

**To restart**, either click AUTOSTART on the realm-picker page, or:

```bash
python -m minecraftmgr realm start <id>
# or:
python -m minecraftmgr realm start --all
```

`realm start` refuses (rather than racing a second process) if a screen
session for that realm is already up. `realm stop` sends the in-game `stop`
console command and polls for up to 10 seconds, falling back to
`pgrep`+`kill` if the session is still there — `screen -X stuff` doesn't
always reach the console reliably (hit twice before, converting jitterbug).

### Manual fallback

If the CLI isn't available (or for a one-off outside the registry), the
underlying steps are the same ones `stop_realm()`/`start_realm()` automate:

```bash
sudo -iu minecraft
screen -ls
# find the session named after the realm's data_dir
screen -r <data_dir>
```

Inside the attached session, type the in-game console command:

```
stop
```

Wait for the world to save and the process to exit — the screen session
closes on its own once it does. If it's still there after ~10 seconds,
detach with `Ctrl+A d` and fall back to killing it directly:

```bash
pgrep -f <data_dir>
kill <pid>
```

To start manually:

```bash
cd /opt/mc/<data_dir>
screen -dmS <data_dir> ./start.sh
```

## Verify

- `python -m minecraftmgr realm status <id>` (or with no id, every registered
  realm) reports live `screen` state — same info the AUTOSTART button's
  `GET /status` uses, just from the CLI. Must run as `minecraft`; `screen`
  sessions are per-user, so checking as any other user always looks like
  nothing is running.
- Or, manually: `screen -ls` no longer lists `<data_dir>` (stopped) or lists
  it again (restarted).
- `GET https://trigger.gamenightbymike.com/status` (or the picker page)
  reflects the new state within a few seconds.

## Gotchas

- Killing the process instead of using the in-game `stop` command (skipping
  straight to `pgrep`/`kill` without trying `stop` first) risks losing
  whatever was auto-saved since the last save interval — always try the
  graceful path first, same as `stop_realm()`'s own fallback ordering.
- A realm that's mid-`Done (`-boot (world generation, not yet accepting
  connections) shouldn't be killed either — same reasoning
  `provision_service.first_boot_cycle()` uses for not auto-killing on a
  readiness timeout.
