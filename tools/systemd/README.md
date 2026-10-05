# tools/systemd/

systemd units for oscar that live in this repo. Install steps and day-to-day
commands are in [docs/workflows/reboot-recovery.md](../../docs/workflows/reboot-recovery.md).

| File | Installed as | What |
|---|---|---|
| `velocity-proxy.service` | `/etc/systemd/system/velocity-proxy.service` | Velocity proxy: starts at boot, restarts on any exit, no terminal/JLine (avoids the Java 25 crash) |
| `minecraft-autostart-stop.conf` | `/etc/systemd/system/minecraft-autostart.service.d/stop.conf` | Makes the existing realm autostart unit stop running realms cleanly on shutdown |

Already on oscar but not (yet) tracked here: `minecraft-autostart.service`,
`mc-trigger.service`, `cloudflared-mc-trigger.service` (copies in
`/opt/mc/readme/`).
