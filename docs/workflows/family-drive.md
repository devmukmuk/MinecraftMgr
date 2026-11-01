# Family drive: P: on Mom and Dad's Utah PCs (Cloudflare Tunnel + Access)

**Automation status:** Partly scripted. oscar's side is
`tools/scripts/family-drive/setup-family-drive.sh` (safe to rerun). Each
Utah PC's drive letter comes from `tools/scripts/family-drive/Map-P-Drive.ps1`.
The Cloudflare dashboard steps are done by hand.

**Status:** Planned 2026-11-01. Not set up yet.

## What Mom and Dad see

- **Family (P:)** under *This PC* in File Explorer. They drag files in and
  out like any other drive.
- The first time, and again whenever the login runs out (7 days, step 3),
  the Cloudflare One icon by the clock says *login required*. Clicking it
  opens a browser page where they type their email, get a 6-digit code by
  email, and type it in. P: then works again.
- A deleted file isn't gone right away. It goes to `P:\.recycle` for 30 days.

## The design, and why

```
Utah PC (P: = \\10.77.77.1\Family)
  └─ Cloudflare One client ──> Cloudflare Access ──> tunnel oscar-family ──> cloudflared (oscar) ──> 10.77.77.1:445 (Samba [Family])
      (signed in by email code)   (Family policy:        (outbound from oscar)
                                   their 2 emails + Mike)
```

- **Why the Cloudflare One client, not `cloudflared` as with SSH.** A mapped
  drive is SMB, and Windows 10 only connects SMB to port 445. That port is
  always in use by Windows itself on the local machine. The SSH trick
  (`cloudflared access ssh` as a `ProxyCommand`) has no SMB equivalent, so
  `cloudflared access tcp` would need a local port that Windows 10 can't
  point a drive at. Cloudflare's supported path for SMB is the **Cloudflare
  One client** (formerly WARP) plus a **private network route** through a
  tunnel. Access still checks the email (one-time PIN) before any traffic
  reaches oscar.
- **Two locks, as with SSH.** Lock 1 is Cloudflare Access: only the emails in
  the `Family` policy, each confirmed by an emailed code. Lock 2 is the Samba
  password for user `family`, which Windows saves once, so they never type it.
- **`10.77.77.1`, not oscar's LAN address.** The Utah router very likely
  uses `192.168.1.x` too. A made-up address on oscar's `lo` can't clash with
  anything in their house (`oscar-family-ip.service`).
- **Only oscar's traffic goes through Cloudflare.** The client runs in
  split-tunnel *Include* mode with just `10.77.77.1/32`. Their browsing,
  email and Netflix go out exactly as before.
- **"Small" is a hard cap.** The share is its own ext4 file,
  `/mnt/overflow/family/family.img` (100 GB, sparse, so it uses only what's
  stored), loop-mounted at `/srv/family`. A full P: can't fill the 8 TB Plex
  disk.
- **Its own tunnel** (`oscar-family`), following the one-tunnel-per-concern
  rule ([CAP-design.md](../epics/CAP-design.md)).
- **Nothing opened on the router or `ufw`.** `cloudflared` reaches Samba on
  `lo`, which `ufw` always allows. The `[Family]` share also has
  `hosts allow` set to localhost, `10.77.77.1` and the home LAN.
- **Free.** Zero Trust Free covers up to 50 users. This adds 2.

### Alternatives considered

| Option | Verdict |
|---|---|
| Port-forward 445 on the router | **Never.** SMB open to the internet is a top ransomware target. |
| `cloudflared access tcp` on each PC | Doesn't work on Windows 10. The drive would have to point at a port other than 445, and only Windows 11 24H2+ can do that. |
| WebDAV over `https://files.gamenightbymike.com` mapped as a drive | Windows' WebDAV client can't show the Access sign-in page, so it just fails. Hostnames behind Access only work in a browser or with `cloudflared`. |
| Tailscale (already on oscar) | Works and is simpler, but sign-in is a Google/Microsoft account rather than an email code through your existing Cloudflare setup. Good fallback; see the end. |
| Nextcloud (already in docker) | A browser/app experience, not a drive letter. More to maintain. |

## Step 1: oscar (as `mike`, at home or through `ssh oscar-remote`)

```bash
cd /srv/mc && git pull
sudo bash tools/scripts/family-drive/setup-family-drive.sh
```

It asks for one thing: **the Samba password for `family`**. Pick something
long and save it in your password manager. You'll type it once on each Utah
PC. For a bigger or smaller drive: `FAMILY_SIZE=200G sudo bash ...`. The
size only applies the first time.

What it does, in order (each step is skipped if already done):

1. Installs `oscar-family-ip.service`, which puts `10.77.77.1/32` on `lo`.
2. Creates the no-login system user `family` and sets its Samba password.
3. Creates the sparse image, formats it (`ext4`, label `family`), and adds
   an fstab line (`loop,nofail`, after `/mnt/overflow`). It backs up fstab
   first, then mounts the image at `/srv/family`, owned by `family`, mode 2775.
4. Appends `[Family]` to `/etc/samba/smb.conf` (backing it up first) with the
   recycle bin, runs `testparm`, and reloads `smbd`. It also installs
   `/etc/cron.daily/family-drive-recycle`, which empties anything older than
   30 days.
5. As `mike`: `cloudflared tunnel create oscar-family`,
   `tunnel route ip add 10.77.77.1/32 oscar-family`, and writes
   `~/.cloudflared/oscar-family-config.yml` (`warp-routing` on, no hostnames).
6. Installs and starts `cloudflared-oscar-family.service`.

Check:

```bash
systemctl status cloudflared-oscar-family oscar-family-ip --no-pager
cloudflared tunnel route ip show          # 10.77.77.1/32 -> oscar-family
smbclient -L 10.77.77.1 -U family         # lists Family
df -h /srv/family                         # ~98G, its own filesystem
```

`\\oscar\Family` also works on the home LAN for you (user `mike`). Files you
put there show as owned by `family`.

## Step 2: Turn on email codes (Cloudflare dashboard, once)

dash.cloudflare.com → **Zero Trust** (team `purple-credit-d919`).

1. **Integrations → Identity providers → Add new → One-time PIN.** Today the
   only login method is your Cloudflare account (see
   [remote-ssh-travel.md](remote-ssh-travel.md#login-method-cloudflare-account-not-one-time-pin)).
   Mom and Dad need the emailed-code option. With *Accept all available
   identity providers* on, the SSH app shows it too. That's harmless; the
   `Mike only` policy still decides who gets in.
2. **Settings → Network → Firewall: Proxy → TCP on** (UDP too, if offered).
   Access for private-network apps needs Gateway to proxy the traffic.

## Step 3: The Access application for the share

**Access controls → Applications → Create new application → Self-hosted and
private → Continue with Self-hosted and private.**

- **Destinations → Private IPs:** `10.77.77.1`, port `445`, protocol TCP.
  No public hostname.
- **Access policies:** create `Family`, Action **Allow**,
  Include → **Emails** → Mom's email, Dad's email, and yours (so you can test).
- **Authentication:** leave *Accept all available identity providers* on.
- **Details:** Name `Family drive`, **Session Duration `7 days`**. This is
  how often they get the email-code prompt. A shorter value means more
  prompts; up to `1 month` is fine for them.
- Check **Preview** before Create: the policy and `10.77.77.1:445` must both
  show.

## Step 4: Who may install the client, and how it routes

1. **Settings → WARP Client → Device enrollment permissions → Manage → Add a
   rule:** Allow, Include → Emails → the same three addresses. Login method:
   One-time PIN.
2. **Settings → WARP Client → Device settings → Default profile → Edit:**
   - **Split Tunnels → Include IPs and domains.** The list holds only
     `10.77.77.1/32` (description `oscar Family drive`). The default *Exclude*
     mode excludes `10.0.0.0/8`, which would stop the share from working.
   - **Service mode: Traffic and DNS** (the default) is fine.
   - **Allow device to leave organization:** off, so the client isn't
     signed out by accident.
   - **Show notifications** (or *Allow updates* / *Auto connect*, wherever
     the version puts them): turn on *Auto connect* (0 min). Then the client
     reconnects by itself after a restart.

If you ever enroll another device (Foxtrot for testing) and don't want it
in Include mode, make a second profile scoped by email instead of changing
the default one.

## Step 5: Each Utah PC (Windows 10, 64-bit)

Do this on a visit, or with them over a screen-share (Quick Assist is built
into Windows 10).

1. Install the client: **https://one.one.one.one** → *Windows*, or
   `winget install --id Cloudflare.Warp`. The tray icon is the orange
   Cloudflare cloud.
2. Click the icon → gear → **Preferences → Account → Login with Cloudflare
   Zero Trust**. Team name: **`purple-credit-d919`**. In the browser: their
   email → **Send me a code** → type the code from the email. The client
   shows **Connected** and the "Zero Trust" label.
3. Copy `Map-P-Drive.ps1` to the PC (a USB stick, or email it to yourself and
   download it there). Then in a normal PowerShell:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\Map-P-Drive.ps1
   ```

   It checks that the client is connected and that oscar answers on 445. It
   asks for the `family` password, saves it in Windows Credential Manager
   (`cmdkey`), maps `P:` as persistent, and labels it **Family**.
4. Open **File Explorer → This PC → Family (P:)**. Drop a test file in, and
   check that you can see it on oscar: `ls -l /srv/family`.

Done by hand instead of the script:
`cmdkey /add:10.77.77.1 /user:family /pass:<pw>`, then
`net use P: \\10.77.77.1\Family /persistent:yes`.

## Step 6: Test from Foxtrot first (optional, recommended)

Before a visit, try it on Foxtrot. Install the client, sign in with your own
email (in the `Family` policy), then run `Map-P-Drive.ps1 -Letter Q`. This
proves the whole path from outside the house. Afterwards, sign Foxtrot out
of the client, or keep it if Include mode with one IP doesn't bother you.

## Day to day / support calls

| They say | Cause | Fix |
|---|---|---|
| "P: has a red X" after starting the PC | Windows tried P: before the client connected | Double-click P:. It reconnects. If not, see the next rows. |
| "It wants an email code" | The 7-day Access session ran out | Click the Cloudflare notification (or the tray icon), type the email, type the code. |
| "Cloudflare says Disconnected" | Client switched off | Tray icon → turn the switch on. |
| "Access denied / That account does not have access" | Signed in with a different email than the policy lists | Check the `Family` policy emails (step 3) and device enrollment (step 4). |
| P: asks for a username/password | The saved credential is gone, or you changed the password | Run `Map-P-Drive.ps1` again. |
| "Out of space" | 100 GB cap reached (check `df -h /srv/family`) | Empty `/srv/family/.recycle`, or grow it: see below. |
| Nothing works for anyone | oscar or the tunnel is down | `systemctl status cloudflared-oscar-family`. After a power cut, see [reboot-recovery.md](reboot-recovery.md). |

**Growing the drive** (on oscar):

```bash
sudo umount /srv/family
sudo truncate -s 200G /mnt/overflow/family/family.img
sudo e2fsck -f /mnt/overflow/family/family.img && sudo resize2fs /mnt/overflow/family/family.img
sudo mount /srv/family
```

**Backups:** restic's `critical` set includes `/srv` (except `/srv/plex`).
Check that the next snapshot shows `/srv/family`
(`restic ls latest /srv/family | head`). If restic runs with
`--one-file-system`, add `/srv/family` to its paths.

## If a PC is lost, or someone shouldn't have access any more

1. Zero Trust → **My Team → Devices**: revoke that device. Also remove the
   email from the `Family` policy (step 3) and device enrollment (step 4) if
   needed.
2. Change the share password on oscar (`sudo smbpasswd family`), then run
   `Map-P-Drive.ps1` again on the PC that's still in use.

## Undo / tear down

```bash
sudo systemctl disable --now cloudflared-oscar-family oscar-family-ip
sudo rm /etc/systemd/system/{cloudflared-oscar-family,oscar-family-ip}.service && sudo systemctl daemon-reload
cloudflared tunnel route ip delete 10.77.77.1/32
cloudflared tunnel delete oscar-family
# remove [Family] from /etc/samba/smb.conf, reload smbd; remove the fstab line;
# rm /etc/cron.daily/family-drive-recycle; the files stay in family.img until you delete it
```

Then delete the `Family drive` Access application, the enrollment rule and
the Include entry in the dashboard. On each PC, uninstall Cloudflare One
and run `net use P: /delete`.

## Tailscale instead

If the Cloudflare One client gives trouble on their PCs: Tailscale is
already on oscar (`100.123.140.31`). Install Tailscale on each Utah PC,
share oscar to their accounts (admin console → oscar → *Share*), and map
`P:` to `\\100.123.140.31\Family` with the same script
(`-Server 100.123.140.31`). Add `100.123.140.31` to the share's
`hosts allow` first. They sign in with Google/Microsoft instead of an email
code.
