# SSH to oscar while traveling (Cloudflare Tunnel + Access)

**Automation status:** None. This is a one-time setup on oscar, in the
Cloudflare dashboard, and on Foxtrot. After that, `ssh oscar-remote` works
from any network.

**Status:** Live since 2026-10-30. Set up from Foxtrot by following this
doc. Where the real setup differed from the plan, this doc now describes
what actually happened.

## Day to day

| Where you are | Command (on Foxtrot) |
|---|---|
| Home LAN | `ssh oscar` |
| Anywhere, home included | `ssh oscar-remote` |

The first `ssh oscar-remote` in each 24 h opens a browser on the Cloudflare
Access sign-in page. Sign in with your Cloudflare account and SSH continues
by itself.

## The design, and why

```
Foxtrot ──ssh──> cloudflared (Foxtrot) ──HTTPS──> Cloudflare Access ──> tunnel ──> cloudflared (oscar) ──> localhost:22
                                           (Cloudflare account login)  (outbound from oscar)
```

- **No router or `ufw` change.** `cloudflared` on oscar makes an *outbound*
  connection to Cloudflare, the same way `trigger.gamenightbymike.com` and
  `shots.gamenightbymike.com` already work. Port 22 stays closed to the
  internet, so internet-wide SSH scanners never reach it.
- **Two locks, not one.** To get in, you first have to pass Cloudflare Access:
  Cloudflare checks your login and the `Mike only` email policy before any
  traffic reaches oscar. After that, you still need an SSH key listed in
  `~mike/.ssh/authorized_keys`. Losing one of them isn't enough to get in.
- **Its own tunnel** (`oscar-ssh`), not an extra ingress rule on `mc-trigger`.
  That follows the existing one-tunnel-per-concern rule
  ([CAP-design.md](../epics/CAP-design.md)), so restarting or breaking one
  doesn't affect the other.
- **Free.** Zero Trust is on the Free plan, which covers up to 50 users.

### Alternatives considered

| Option | Verdict |
|---|---|
| Port-forward 22 (or another port) on the AT&T router → oscar | **Don't.** It exposes `sshd` to the entire internet, and changing the port only cuts log noise. If you ever do it anyway, use key-only auth (step 1) plus `fail2ban`. |
| **Tailscale** (install on oscar and Foxtrot, then `ssh mike@oscar` over the tailnet) | A good choice, and the simplest one for a single admin. It also makes the `\\oscar\Minecraft` SMB share and every LAN port reachable while you're away. It's not the main choice here because it adds a new account and a new always-on daemon, when Cloudflare is already in use. See [Tailscale instead](#tailscale-instead) at the end. |
| Cloudflare Tunnel **without** an Access application | **Don't.** Anyone could then reach `sshd` through the hostname. Key-only auth would still protect it, but you'd lose the first lock. |

## Before you start: confirm which key Foxtrot uses

On Foxtrot, at home, in a **normal (not admin) PowerShell**. A normal window
may still open in `C:\WINDOWS\system32`; check that the title bar doesn't say
"Administrator".

```powershell
ssh -o PasswordAuthentication=no oscar exit
ssh -v -o PasswordAuthentication=no oscar exit 2>&1 | Select-String "Server accepts key|Authenticated"
```

The first command must log in and exit without asking for a password. The
second prints the key oscar actually accepted (`Server accepts key: ...`).
On Foxtrot that's **`~/.ssh/id_ed25519_oscar`**. Plain `id_ed25519` is the
GitHub key. Use the name it prints in step 5.

## Step 1: Make oscar's sshd key-only (on oscar, as `mike`)

See what's in effect now:

```bash
sudo sshd -T | grep -Ei '^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin|pubkeyauthentication) '
```

On oscar (2026-10-30), passwords were already off. That command printed:

```
permitrootlogin without-password
pubkeyauthentication yes
passwordauthentication no
kbdinteractiveauthentication no
```

The only gap was `without-password`, which means `root` can still log in
with a key. Before turning that off, check that nothing logs in as root:

```bash
sudo cat /root/.ssh/authorized_keys 2>/dev/null || echo "no root keys"
```

The file was empty (nothing printed), so turning it off was safe:

```bash
echo 'PermitRootLogin no' | sudo tee /etc/ssh/sshd_config.d/10-key-only.conf
sudo sshd -t && sudo systemctl reload ssh
sudo sshd -T | grep -i '^permitrootlogin'      # permitrootlogin no
```

If `sshd -T` had shown passwords still on, the same drop-in would also need
`PasswordAuthentication no` and `KbdInteractiveAuthentication no`. For each
setting, sshd keeps the first value it reads, and it reads the drop-ins in
name order. That's why the file is named `10-...`: it wins over
`50-cloud-init.conf`, which on some Ubuntu installs sets
`PasswordAuthentication yes`.

**Keep that session open.** From a second terminal, `ssh oscar` must still
work before you close the first one. If it doesn't, undo the change from the
session that's still open:
`sudo rm /etc/ssh/sshd_config.d/10-key-only.conf && sudo systemctl reload ssh`.

## Step 2: Create the Access application *first* (Cloudflare dashboard)

Do this before the tunnel exists, so the hostname is never reachable without
the login check.

1. dash.cloudflare.com → **Zero Trust** in the left menu (it opens
   "Cloudflare One"). Zero Trust was already set up on the **Free** plan
   from the earlier tunnels, so there was no team-name or plan screen.
2. **Access controls → Applications → Create new application**.
   - Type: **Self-hosted and private**. The "Example configuration"
     dropdown underneath only changes the diagram; leave it on
     **Public DNS**. Then click **Continue with Self-hosted and private**.
3. **Application details** tab:
   - **Destinations → Public hostnames:** subdomain `ssh`, domain
     `gamenightbymike.com`, no path. Don't add private hostnames or IPs.
     Those are for the Cloudflare One (WARP) client, which isn't used here.
   - **Access policies:** create a policy and attach it to the app:
     - Name `Mike only`, Action **Allow**
     - Include → **Emails** → the email on your Cloudflare account, and nothing else
     - No Require or Exclude rules
   - **Authentication:** leave **Accept all available identity providers**
     on. On this account that's only **Cloudflare** (your Cloudflare
     dashboard login). See [Login method](#login-method-cloudflare-account-not-one-time-pin).
     Leave **Authenticate with Cloudflare One Client** off.
   - **Details:** Name `oscar SSH`, Session Duration `24 hours`.
4. **Before clicking Create**, check the **Preview** box. It must show the
   policy under Policies and `ssh.gamenightbymike.com` under Destinations.
   If either says "No policies added" or "No destinations assigned", fix it
   first.
5. **Create.** The Applications list then shows `oscar SSH` →
   `ssh.gamenightbymike.com`.

### Login method: Cloudflare account, not One-time PIN

The plan was a one-time PIN emailed to you, but One-time PIN had never been
added as a login method on this account. The sign-in page only offered
**Cloudflare**, which logs you in with your Cloudflare dashboard account.
That works fine and is what's in use now. It does mean your Cloudflare
account is the first lock, so **keep two-factor turned on for it**
(dash.cloudflare.com → My Profile → Authentication).

To add One-time PIN as a second option, for example for a device where
you're not logged in to Cloudflare: **Integrations → Identity providers →
Add new → One-time PIN**. With "Accept all available identity providers" on,
it then shows up on the sign-in page by itself.

## Step 3: Create the tunnel (on oscar, as `mike`, no sudo)

`mike` is already logged in to `cloudflared` (`~/.cloudflared/cert.pem`,
from the earlier tunnels).

```bash
ls ~/.cloudflared/cert.pem
cloudflared tunnel create oscar-ssh
cloudflared tunnel route dns oscar-ssh ssh.gamenightbymike.com   # "Added CNAME ssh.gamenightbymike.com ..."
```

Write the config. This looks up the tunnel ID itself, so there's nothing to
paste by hand:

```bash
TID=$(cloudflared tunnel list --name oscar-ssh -o json | python3 -c 'import sys,json; print(json.load(sys.stdin)[0]["id"])')
echo "tunnel id: $TID"
cat > ~/.cloudflared/oscar-ssh-config.yml <<EOF
tunnel: $TID
credentials-file: /home/mike/.cloudflared/$TID.json
ingress:
  - hostname: ssh.gamenightbymike.com
    service: ssh://localhost:22
  - service: http_status:404
EOF
cat ~/.cloudflared/oscar-ssh-config.yml
cloudflared tunnel --config ~/.cloudflared/oscar-ssh-config.yml ingress validate   # OK
```

The live tunnel ID is `cecfacf7-29ee-4ba2-b9e0-efbcaf739a25`. Commands
print a "Your version ... is outdated" warning: oscar runs `cloudflared`
2026.7.3. That's harmless here; upgrading it is separate work.

## Step 4: Run it as a service, so it survives reboots (on oscar, as `mike`)

```bash
cd /srv/mc && git pull
sudo cp /srv/mc/tools/systemd/cloudflared-oscar-ssh.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cloudflared-oscar-ssh.service
systemctl status cloudflared-oscar-ssh --no-pager    # active (running)
cloudflared tunnel info oscar-ssh                     # one connector, edges like 1xmia04, 1xmia10
```

The log shows a few `WRN`/"failed to ..." lines about ICMP proxying and
ping groups. They're harmless: SSH doesn't use ICMP.

The unit uses `Restart=always` rather than the `on-failure` that
`cloudflared-mc-trigger` uses. This tunnel is the only way back in while
you're away, so it should come back whatever made it stop.

## Step 5: Set up Foxtrot (normal PowerShell)

```powershell
winget install --id Cloudflare.cloudflared
# open a NEW terminal so PATH picks it up, then:
cloudflared --version          # 2026.10.6 on 2026-10-30
where.exe cloudflared          # C:\Program Files (x86)\cloudflared\cloudflared.exe
notepad $env:USERPROFILE\.ssh\config
```

Add this below the existing `Host oscar` block. Use the key name from
[Before you start](#before-you-start-confirm-which-key-foxtrot-uses):

```
# Anywhere else, through Cloudflare Access
Host oscar-remote
  HostName ssh.gamenightbymike.com
  User mike
  IdentityFile ~/.ssh/id_ed25519_oscar
  IdentitiesOnly yes
  ProxyCommand cloudflared access ssh --hostname %h
  ServerAliveInterval 30
```

`IdentitiesOnly yes` matters because Foxtrot holds three keys (personal
GitHub, devmukmuk GitHub, oscar). Without it, `ssh` offers the GitHub keys
first and can run into sshd's limit on failed authentication attempts.

If `ssh` can't find `cloudflared`, use the full quoted path:
`ProxyCommand "C:\Program Files (x86)\cloudflared\cloudflared.exe" access ssh --hostname %h`.

(Linux/macOS: same `Host` block. Install with `brew install cloudflared` or
Cloudflare's apt repo.)

## Step 6: Test

```powershell
ssh oscar-remote
```

1. A browser opens **"Log in to oscar SSH"** on
   `<team>.cloudflareaccess.com`. Click **Cloudflare** and sign in with your
   Cloudflare account. The token is cached in
   `%USERPROFILE%\.cloudflared\` for 24 h.
2. Back in PowerShell, answer **yes** to the new host key prompt. It's a new
   hostname, so it gets its own `known_hosts` entry.
3. You land at `mike@oscar`.

**Testing from home Wi-Fi is enough.** With a router port-forward, a test
from inside the LAN can be misleading. A tunnel works differently: `ssh
oscar-remote` always goes out to Cloudflare and back through the tunnel, so
seeing the Access sign-in page proves the whole path works. A phone hotspot
isn't needed. On 2026-10-30 it didn't work with the phone's Wi-Fi off, and
the home test was used instead. The only thing a home test can't show is a
remote network (hotel, office) that blocks Cloudflare. That's rare; a café
or friend's Wi-Fi checks it.

Also check that the first lock is really there: open
`https://ssh.gamenightbymike.com` in a private browser window. It should show
the Cloudflare Access sign-in page, **not** an error or anything from oscar.

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

## Before a trip

- [ ] Two-factor is on for the Cloudflare account (it's the first lock).
- [ ] oscar's BIOS has **Restore on AC power loss → Power On**
      ([reboot-recovery.md](reboot-recovery.md)). Without it, a power cut
      leaves oscar off and unreachable.
- [ ] `ssh oscar-remote` works from Foxtrot within the last few days.

## If something goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| Sign-in page shows **"That account does not have access."** | Login worked, but the `Mike only` policy didn't match. This happened during setup and the policy had to be fixed. | Access controls → Applications → oscar SSH → Edit: the policy must be **attached** to the app, Action **Allow**, Include **Emails** = exactly the address you signed in with (your Cloudflare account email), with no Require/Exclude rules. Save, then retry (use a private window if the browser keeps the error). |
| Sign-in page only offers **Cloudflare**, and you expected an email code | One-time PIN isn't added on the account | Use Cloudflare, or add One-time PIN ([Login method](#login-method-cloudflare-account-not-one-time-pin)). |
| `websocket: bad handshake` / `failed to connect to origin` | Tunnel down on oscar, or oscar is off | If you're away, there's nothing to do over SSH. Check `cloudflared tunnel info oscar-ssh` from any machine logged in to `cloudflared`, or ask someone at home to power-cycle oscar. |
| `Permission denied (publickey)` | Access passed but the key isn't authorized | Wrong `IdentityFile` (on Foxtrot it's `id_ed25519_oscar`, not `id_ed25519`), or the key isn't in `~mike/.ssh/authorized_keys`. |
| `Too many authentication failures` | `ssh` offered other keys first | Add `IdentitiesOnly yes` to the `Host oscar-remote` block. |
| `cloudflared: not found` / `CreateProcess failed` | `cloudflared` isn't on PATH for `ssh` | Open a new terminal after installing, or use the full quoted path in `ProxyCommand` (step 5). |
| Host key warning on `oscar-remote` after you rebuilt oscar | Expected after a reinstall | `ssh-keygen -R ssh.gamenightbymike.com`, and only after confirming that's really why. |

## If Foxtrot is lost or stolen

From any browser, phone included:

1. Zero Trust → **Access controls → Applications → oscar SSH**: revoke
   existing sessions (or temporarily change the policy to *Block*). This
   locks out the laptop's cached Access token right away.
2. Change the Cloudflare account password if the laptop was logged in to
   the dashboard.
3. When you're back, or from another trusted machine: remove Foxtrot's
   `id_ed25519_oscar.pub` line from `~mike/.ssh/authorized_keys` on oscar,
   then put the policy back to Allow.

## Undo / tear down

```bash
sudo systemctl disable --now cloudflared-oscar-ssh.service
sudo rm /etc/systemd/system/cloudflared-oscar-ssh.service && sudo systemctl daemon-reload
cloudflared tunnel delete oscar-ssh
```

Then delete the `ssh` DNS record and the `oscar SSH` Access application in
the Cloudflare dashboard. `/etc/ssh/sshd_config.d/10-key-only.conf` can
stay; it's worth keeping regardless.

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
