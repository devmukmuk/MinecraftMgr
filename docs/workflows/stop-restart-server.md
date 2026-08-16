# Stop / restart a realm

**Automation status:** Partial. **Starting** is fully automated (the
realm-picker page's AUTOSTART button, or `trigger_service.start_realm()`
underneath it). **Stopping** has working, tested logic
(`trigger_service.stop_realm()`) but no CLI command or HTTP endpoint exposes
it yet — it's currently only called internally by `provision`/`activate`'s
first-boot cycle. Proposed as `realm stop <id>` in
[PROV-design.md](../epics/PROV-design.md#future-work-modifying-an-already-active-realm).

## When to use

Any workflow that says "stop the realm first" — [change-port](change-port.md),
[update-jar-version](update-jar-version.md), editing `server.properties`
directly. Also useful on its own to free up memory on oscar for a realm
nobody's using, without deregistering it.

## Steps (manual, today)

As the `minecraft` user on oscar — **only `minecraft` may do this**, never
the `mike` automation key:

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
closes on its own once it does. If it's still there after ~10 seconds
(this has happened twice before — `screen -X stuff` doesn't always reach the
console reliably), detach with `Ctrl+A d` and fall back to killing it
directly:

```bash
pgrep -f <data_dir>
kill <pid>
```

**To restart**, either click AUTOSTART on the realm-picker page, or from the
`minecraft` shell:

```bash
cd /opt/mc/<data_dir>
screen -dmS <data_dir> ./start.sh
```

## Verify

- `screen -ls` no longer lists `<data_dir>` (stopped) or lists it again
  (restarted).
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
