# SSH to oscar while traveling (Cloudflare Tunnel + Access)

**Automation status:** None. This is a one-time setup on oscar, in the
Cloudflare dashboard, and on Foxtrot. After that, `ssh oscar-remote` works
from any network.

## The design, and why

```
Foxtrot ──ssh──> cloudflared (Foxtrot) ──HTTPS──> Cloudflare Access ──> tunnel ──> cloudflared (oscar) ──> localhost:22
                                              (email one-time PIN)      (outbound from oscar)
```

- **No router or `ufw` change.** `cloudflared` on oscar makes an *outbound*
  connection to Cloudflare, the same way `trigger.gamenightbymike.com` and
  `shots.gamenightbymike.com` already work. Port 22 stays closed to the
  internet, so internet-wide SSH scanners never reach it.
- **Two locks, not one.** To get in, you need to pass Cloudflare Access (a
  one-time PIN sent to your email, checked by Cloudflare before any traffic
  reaches oscar) *and* have an SSH key in `~mike/.ssh/authorized_keys`.
  Losing one of them isn't enough to get in.
- **Its own tunnel** (`oscar-ssh`), not an extra ingress rule on `mc-trigger`.
  That follows the existing one-tunnel-per-concern rule
  ([CAP-design.md](../epics/CAP-design.md)), so restarting or breaking one
  doesn't affect the other.
- **Free.** Cloudflare Zero Trust's free plan covers up to 50 users.

### Alternatives considered

| Option | Verdict |
|---|---|
| Port-forward 22 (or another port) on the AT&T router → oscar | **Don't.** It exposes `sshd` to the entire internet, and changing the port only cuts log noise. If you ever do it anyway, use key-only auth (step 1) plus `fail2ban`. |
| **Tailscale** (install on oscar and Foxtrot, then `ssh mike@oscar` over the tailnet) | A good choice, and the simplest one for a single admin. It also makes the `\\oscar\Minecraft` SMB share and every LAN port reachable while you're away. It's not the main choice here because it adds a new account and a new always-on daemon, when Cloudflare is already in use. See [Tailscale instead](#tailscale-instead) at the end. |
| Cloudflare Tunnel **without** an Access application | **Don't.** Anyone could then reach `sshd` through the hostname. Key-only auth would still protect it, but you'd lose the first lock. |

## Before you start

- On the LAN, `ssh oscar` from **Foxtrot** already works with a key (not a
  password). Check this now: `ssh -o PasswordAuthentication=no oscar`. If
  it fails, add Foxtrot's public key to oscar's `~/.ssh/authorized_keys`
  first (`type $env:USERPROFILE\.ssh\id_ed25519.pub` on Foxtrot, then append
  that line on oscar).
- **Do all of this at home, at least a day before you leave**, and test from
  a phone hotspot (step 6). If something is wrong, you won't be able to fix
  it from the road.

## Step 1 — Make oscar's sshd key-only (on oscar, as `mike`)

See what's in effect now:

```bash
sudo sshd -T | grep -Ei '^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin|pubkeyauthentication) '
```

If that doesn't already show `passwordauthentication no`,
`kbdinteractiveauthentication no`, `permitrootlogin no`, and
`pubkeyauthentication yes`, add a drop-in:

```bash
sudo tee /etc/ssh/sshd_config.d/10-key-only.conf >/dev/null <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
EOF
sudo sshd -t && sudo systemctl reload ssh
```

**Keep your current SSH session open.** Then, from a *second* terminal on
Charlie and on Foxtrot, run `ssh oscar`. Both must still get in before you
close the first session. If either fails, delete the drop-in and run
`sudo systemctl reload ssh` again from the session that's still open.

For each setting, sshd keeps the first value it reads, and it reads the
drop-ins in name order. That's why the file is named `10-...`: it then wins
over `50-cloud-init.conf`, which on some Ubuntu installs sets
`PasswordAuthentication yes`. Run `sshd -T` again after reloading to confirm
the values actually in effect.

## Step 2 — Create the Access application *first* (Cloudflare dashboard)

Do this before the tunnel exists, so the hostname is never reachable without
the PIN check.

1. Go to <https://one.dash.cloudflare.com> → Zero Trust. The first time,
   it asks for a team name (anything, e.g. `gamenight`) and a plan: pick
   **Free**. (It may ask for a payment method even for the free plan.)
2. **Access → Applications → Add an application → Self-hosted.**
   - Application name: `oscar SSH`
   - Session duration: `24 hours` (how often Foxtrot asks for a new PIN)
   - Application domain: subdomain `ssh`, domain `gamenightbymike.com`
3. **Add a policy:**
   - Policy name: `Mike only`
   - Action: **Allow**
   - Include → **Emails** → *your own email address* (only that one)
4. Identity providers: leave **One-time PIN** on (it's on by default).
5. Save.

## Step 3 — Create the tunnel (on oscar, as `mike`, no sudo)

`mike` is already logged in to `cloudflared` (`~/.cloudflared/cert.pem`),
from setting up the earlier tunnels.

```bash
cloudflared tunnel create oscar-ssh          # prints the tunnel ID and writes ~/.cloudflared/<ID>.json
cloudflared tunnel route dns oscar-ssh ssh.gamenightbymike.com

cat > ~/.cloudflared/oscar-ssh-config.yml <<'EOF'
tunnel: oscar-ssh
credentials-file: /home/mike/.cloudflared/<TUNNEL-ID>.json
ingress:
  - hostname: ssh.gamenightbymike.com
    service: ssh://localhost:22
  - service: http_status:404
EOF
# replace <TUNNEL-ID> with the ID printed above:
nano ~/.cloudflared/oscar-ssh-config.yml
cloudflared tunnel --config ~/.cloudflared/oscar-ssh-config.yml ingress validate
```

## Step 4 — Run it as a service, so it survives reboots (on oscar, as `mike`)

```bash
cd /srv/mc && git pull
sudo cp /srv/mc/tools/systemd/cloudflared-oscar-ssh.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cloudflared-oscar-ssh.service
systemctl status cloudflared-oscar-ssh --no-pager    # active (running)
cloudflared tunnel info oscar-ssh                     # shows live connections
```

The unit uses `Restart=always` rather than the `on-failure` that
`cloudflared-mc-trigger` uses. This tunnel is the only way back in while
you're away, so it should come back whatever made it stop.

## Step 5 — Set up Foxtrot (Windows, PowerShell)

```powershell
winget install --id Cloudflare.cloudflared
# open a new terminal so PATH picks it up, then:
cloudflared --version
```

Add this to `%USERPROFILE%\.ssh\config` on Foxtrot. Keep the existing
`Host oscar` entry for when you're home:

```
# Home LAN
Host oscar
    HostName 192.168.1.113
    User mike
    IdentityFile ~/.ssh/id_ed25519

# Anywhere else, through Cloudflare Access
Host oscar-remote
    HostName ssh.gamenightbymike.com
    User mike
    IdentityFile ~/.ssh/id_ed25519
    ProxyCommand cloudflared access ssh --hostname %h
    ServerAliveInterval 30
```

If `ssh` can't find `cloudflared`, run `where.exe cloudflared` and use the
full quoted path instead:
`ProxyCommand "C:\Program Files (x86)\cloudflared\cloudflared.exe" access ssh --hostname %h`.

(Linux/macOS: same `Host` block. Install with `brew install cloudflared` or
Cloudflare's apt repo.)

## Step 6 — Test from off the LAN (before you leave)

Turn on your phone's hotspot and disconnect Foxtrot from home Wi-Fi.
Connecting from inside the LAN still goes through Cloudflare, but the hotspot
test is the one that proves it works the way it will on the road.

```powershell
ssh oscar-remote
```

1. The first time, a browser window opens on the Access login page. Enter
   your email, then the PIN Cloudflare emails you. The token is cached in
   `%USERPROFILE%\.cloudflared\`, so you won't be asked again until the
   session expires (24 h).
2. SSH then accepts the host key once (it's a new hostname, so you get a
   fresh `known_hosts` prompt) and logs you in with your key.

Also check that the first lock is really there: open
`https://ssh.gamenightbymike.com` in a private browser window. It should
show the Cloudflare Access login page, **not** an error or anything from
oscar.

## While traveling: controlling Minecraft

Once you're in, you use the same commands as at home (see
[stop-restart-server.md](stop-restart-server.md)):

```bash
ssh oscar-remote
sudo -iu minecraft                         # asks for mike's sudo password
cd /srv/mc
python -m minecraftmgr realm status
python -m minecraftmgr realm start <id>    # or: realm stop <id>
```

- **You don't need SSH to start a realm.** The Autostart button on
  minecraft.gamenightbymike.com already works from anywhere (family PIN).
- **Copying files:** `scp`/`sftp` use the same alias, e.g.
  `scp oscar-remote:/mnt/backup/minecraft/<file>.tar.gz .`. The
  `\\oscar\Minecraft` SMB share is LAN-only and stays that way.
- **Velocity, logs, reboots:** see [reboot-recovery.md](reboot-recovery.md).
  If you reboot oscar from the road, the tunnel comes back on its own at
  boot. Give it a minute or two before reconnecting.

## If something goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| `websocket: bad handshake` / `failed to connect to origin` | Tunnel down on oscar, or oscar is off | If you're away, there's nothing to do over SSH. Check `cloudflared tunnel info oscar-ssh` from any machine logged in to `cloudflared`, or ask someone at home to power-cycle oscar. Check the BIOS "Restore on AC power loss → Power On" setting *before* the trip ([reboot-recovery.md](reboot-recovery.md)). |
| Browser login page loops / "not authorized" | The email you typed isn't the one in the Access policy | Use the exact address from step 2.3. |
| `Permission denied (publickey)` | Access passed but the key isn't authorized | Wrong `IdentityFile`, or Foxtrot's public key isn't in `~mike/.ssh/authorized_keys`. |
| `ssh: ... cloudflared: not found` / `CreateProcess failed` | `cloudflared` isn't on PATH for `ssh` | Use the full quoted path in `ProxyCommand` (step 5). |
| Host key warning on `oscar-remote` after you rebuilt oscar | Expected after a reinstall | `ssh-keygen -R ssh.gamenightbymike.com`, and only after confirming that's really why. |

## If Foxtrot is lost or stolen

From any browser, phone included:

1. Zero Trust dashboard → **Access → Applications → oscar SSH** → revoke
   existing sessions (or temporarily change the policy to *Block*). This
   locks out the laptop's cached Access token right away.
2. When you're back, or from another trusted machine: remove Foxtrot's
   line from `~mike/.ssh/authorized_keys` on oscar, then put the policy back
   to Allow.

Because both locks are needed, someone holding the laptop still can't get in
unless they can also read your email.

## Undo / tear down

```bash
sudo systemctl disable --now cloudflared-oscar-ssh.service
sudo rm /etc/systemd/system/cloudflared-oscar-ssh.service && sudo systemctl daemon-reload
cloudflared tunnel delete oscar-ssh
```

Then delete the `ssh` DNS record and the `oscar SSH` Access application in
the Cloudflare dashboard.

## Tailscale instead

If you'd rather not depend on Cloudflare for SSH:

1. Install on oscar: `curl -fsSL https://tailscale.com/install.sh | sh`, then
   `sudo tailscale up`, and approve it in the browser.
2. Install the Tailscale app on Foxtrot and sign in to the same account.
3. In the Tailscale admin console, **turn off key expiry for oscar**.
   Otherwise oscar drops off the tailnet after 180 days, possibly while
   you're away.
4. From anywhere: `ssh mike@oscar` (MagicDNS), or use oscar's `100.x.y.z`
   address in a `Host oscar-ts` block.

Still do step 1 (key-only sshd). Skip steps 2–5.
