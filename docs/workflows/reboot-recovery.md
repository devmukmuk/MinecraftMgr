# Bring everything back after an oscar reboot

**Automation status:** Full once the [one-time setup](#one-time-setup) below
is installed. After any boot, including after a power cut:

| What | Started by | If it crashes |
|---|---|---|
| Velocity proxy (port 25565) | `velocity-proxy.service` | restarted after 10 s (`Restart=always`) |
| Active realms (up to `max_running_servers`) | `minecraft-autostart.service` (`realm start --all`) | stays down; Autostart button or `realm start <id>` |
| Autostart button / page status | `mc-trigger.service` + `cloudflared-mc-trigger.service` | restarted (`Restart=on-failure`) |

On a planned reboot or shutdown, running realms are stopped cleanly first
(`realm stop --all`), then Velocity. A power cut can't do that: realms lose
anything since their last autosave.

**History:** until 2026-10-05 Velocity ran as a hand-started
`screen -dmS velocity_proxy` session. Nothing started it at boot (found after
the 2026-10-02 reboot: realms up, nobody could connect), and it crashed six
times between 2026-08-16 and 2026-10-05, each time the same Java 25
`upcallLinker.cpp:77 ... wrong thread state for upcall` abort while JLine was
reading console input from the screen terminal (`/opt/mc/_proxy/hs_err_pid*.log`).
The unit runs it with no terminal and JLine off (`-Dterminal.jline=false`),
so that code path never runs, and restarts it if it ever exits anyway.

## One-time setup

The unit files are in the repo, under [`tools/systemd/`](../../tools/systemd/).
As `mike` on oscar (`minecraft` has no sudo), after `cd /srv/mc && git pull`:

```bash
# 1. Install the Velocity unit and the clean-shutdown drop-in for realms.
sudo cp /srv/mc/tools/systemd/velocity-proxy.service /etc/systemd/system/
sudo mkdir -p /etc/systemd/system/minecraft-autostart.service.d
sudo cp /srv/mc/tools/systemd/minecraft-autostart-stop.conf \
        /etc/systemd/system/minecraft-autostart.service.d/stop.conf
sudo systemctl daemon-reload
sudo systemctl enable velocity-proxy.service

# 2. Swap the running screen session for the service (players are dropped for ~5 s).
sudo -u minecraft screen -S velocity_proxy -X quit
sudo systemctl start velocity-proxy.service
systemctl status velocity-proxy.service --no-pager
journalctl -u velocity-proxy -n 20 --no-pager   # ends with "Done (...)!"
```

`which java` should print `/usr/bin/java`; if not, edit `ExecStart` in the
copied unit.

Also check the BIOS once: **Restore on AC power loss → Power On** (name
varies). Without it oscar stays off after a power cut, and none of this runs.

## After a reboot: check

```bash
systemctl status velocity-proxy minecraft-autostart mc-trigger --no-pager
sudo -u minecraft /srv/mc/.venv/bin/python -m minecraftmgr realm status
```

- `velocity-proxy`: `active (running)`.
- `minecraft-autostart`: `active (exited)` (it stays "active" so the shutdown
  stop runs); `journalctl -u minecraft-autostart -b` lists the realms it
  started. Fewer than expected is usually the capacity cap
  (`max_running_servers`, default 3, see
  [stop-restart-server.md](stop-restart-server.md#capacity-cap-2026-08-18)).
- The realm page (minecraft.gamenightbymike.com) shows no red banner.
- Connect to `<realm>.gamenightbymike.com` (no port).

Start anything missing by hand, as `minecraft`:

```bash
sudo -iu minecraft
cd /srv/mc
python -m minecraftmgr realm start --all     # or: realm start <id>
```

## Day to day with the Velocity service

| Task | Command (as `mike`) |
|---|---|
| Apply a `velocity.toml` change | `sudo systemctl restart velocity-proxy` |
| See the log | `journalctl -u velocity-proxy -f` or `/opt/mc/_proxy/logs/latest.log` |
| Stop it (it won't come back until started or rebooted) | `sudo systemctl stop velocity-proxy` |
| Is it up? | `systemctl is-active velocity-proxy`; the page banner also shows it |

There is no Velocity console any more (`screen -r velocity_proxy` is gone).
Console commands like `velocity reload` are replaced by a restart, which
drops connected players for a few seconds.

Don't start Velocity by hand with `screen -dmS velocity_proxy ...` while the
service is enabled: the second copy can't bind 25565 and exits.

If it crash-loops (5 starts in 2 minutes, e.g. a broken `velocity.toml`),
systemd stops trying: fix the file, then
`sudo systemctl reset-failed velocity-proxy && sudo systemctl start velocity-proxy`.

If a JVM crash ever shows up again (new `hs_err_pid*.log` in `/opt/mc/_proxy`),
try Java 21 by changing `ExecStart` to
`/usr/lib/jvm/java-21-openjdk-amd64/bin/java ...` (installed on oscar;
Velocity 3.4+/4 needs 21+).
