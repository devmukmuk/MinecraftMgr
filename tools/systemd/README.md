# tools/systemd/

systemd units for oscar that live in this repo. Install steps and day-to-day
commands are in [docs/workflows/reboot-recovery.md](../../docs/workflows/reboot-recovery.md).

| File | Installed as | What |
|---|---|---|
| `velocity-proxy.service` | `/etc/systemd/system/velocity-proxy.service` | Velocity proxy: starts at boot, restarts on any exit, no terminal/JLine (avoids the Java 25 crash) |
| `minecraft-autostart-stop.conf` | `/etc/systemd/system/minecraft-autostart.service.d/stop.conf` | Makes the existing realm autostart unit stop running realms cleanly on shutdown |
| `cloudflared-oscar-ssh.service` | `/etc/systemd/system/cloudflared-oscar-ssh.service` | Cloudflare Tunnel for SSH from off the LAN. Install steps are in [docs/workflows/remote-ssh-travel.md](../../docs/workflows/remote-ssh-travel.md), not reboot-recovery.md |
| `cloudflared-oscar-family.service` | `/etc/systemd/system/cloudflared-oscar-family.service` | Cloudflare Tunnel with the private route to the Family share. Installed by `tools/scripts/family-drive/setup-family-drive.sh`; see [docs/workflows/family-drive.md](../../docs/workflows/family-drive.md) |
| `oscar-family-ip.service` | `/etc/systemd/system/oscar-family-ip.service` | Puts `10.77.77.1/32` on `lo` for the Family share (same script and doc) |

Already on oscar but not (yet) tracked here: `minecraft-autostart.service`,
`mc-trigger.service`, `cloudflared-mc-trigger.service` (copies in
`/opt/mc/readme/`).
