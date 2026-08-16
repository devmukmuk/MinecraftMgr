# docs/architecture/oscar-realm-hosting.md

Runbook for hosting multiple always-on Minecraft realms on `oscar` (home Ubuntu
box) behind a single subdomain-routed proxy, so players only ever need
`<realm>.gamenightbymike.com` — no port, no port-forward-per-server.

> **Note:** the systemd units described below (Steps 6/7/9) were never
> actually deployed on oscar — realms currently run under `screen`, started
> by hand-maintained scripts. The Velocity proxy described in Step 7 **is
> now live** (deployed 2026-08-16), but only two realms (`gravestone`,
> `jitterbug`) are behind it so far — the other 7 still need their own
> port-forward, `ufw` rule, and Cloudflare `SRV` record (the pattern this
> doc calls out below as the "modded realm exception"). See
> [oscar-migration-plan.md](oscar-migration-plan.md)'s
> [Velocity proxy deployment](oscar-migration-plan.md#velocity-proxy-deployment-live-aug-16-2026)
> section for what deploying it for real actually took, and the per-realm
> steps to bring the rest onto the shared proxy.

Author: Mike Mattinson

## ============= Architecture

```
player types:  gatorland.gamenightbymike.com   (no port)
                        |
                 Cloudflare DNS (CNAME -> mc.gamenightbymike.com, dynamic A record)
                        |
                 home router :25565  --(ONE port-forward rule, ever)-->  oscar LAN IP :25565
                        |
                 Velocity proxy on oscar, reads the hostname the client sent
                        |
        +---------------+----------------+------------------+
        |                |                |                  |
  gatorland:25566   river:25567    gravestones:25568     <next realm>:2556x
  (127.0.0.1 only)  (127.0.0.1)    (127.0.0.1)            (127.0.0.1)
```

Only Velocity is reachable from the internet. Backend servers bind to
`127.0.0.1` and are invisible outside oscar. Adding a realm later = new
backend folder + one line in `velocity.toml` + one Cloudflare CNAME. No new
router rule, ever.

**Caveat — modded (Forge/Fabric) realms:** Velocity/BungeeCord can't carry a
Forge modlist handshake to a backend out of the box. Paper, vanilla, and
Fabric servers using only client-optional or proxy-compatible mods work fine
through the proxy above. A realm that truly needs Forge with server-required
mods should instead get its own dedicated port + DNS `SRV` record (see
"Modded realm exception" at the end) rather than going through Velocity.

## ============= Step 1. Reserve a static LAN IP for oscar

In your router admin UI, find oscar's current DHCP lease and convert it to a
static/reserved lease (bind the reservation to oscar's MAC address). Do this
before setting up the port forward in Step 2, or the forward will silently
break the next time oscar's LAN IP changes.

## ============= Step 2. Port forward (do this once, total)

Router admin UI → port forwarding → forward external TCP `25565` to
`<oscar LAN IP>:25565`. This is the only rule you will ever need, no matter
how many realms you add later, because everything multiplexes through
Velocity on this one port.

## ============= Step 3. Cloudflare DNS

Use one record that tracks your home IP, and CNAME every realm to it:

1. In Cloudflare, create an `A` record: `mc.gamenightbymike.com` → your
   current home public IP. **DNS only** (grey cloud, not orange/proxied) —
   Minecraft's protocol isn't HTTP, so Cloudflare's proxy can't forward it.
2. For each realm, create a `CNAME`: `gatorland` → `mc.gamenightbymike.com`,
   `river` → `mc.gamenightbymike.com`, `gravestones` →
   `mc.gamenightbymike.com`, etc. (also DNS only / grey cloud).

Home ISP IPs usually change. Keep `mc.gamenightbymike.com` in sync
automatically with a small cron job on oscar:

```bash
sudo mkdir -p /opt/ddns
sudo tee /opt/ddns/cloudflare-ddns.sh > /dev/null <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

# Cloudflare API token needs Zone:DNS:Edit for gamenightbymike.com only.
API_TOKEN="REPLACE_ME"
ZONE_ID="REPLACE_ME"
RECORD_NAME="mc.gamenightbymike.com"

CURRENT_IP=$(curl -s https://api.ipify.org)

RECORD_ID=$(curl -s -X GET \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records?type=A&name=${RECORD_NAME}" \
  -H "Authorization: Bearer ${API_TOKEN}" -H "Content-Type: application/json" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['result'][0]['id'])")

curl -s -X PUT \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records/${RECORD_ID}" \
  -H "Authorization: Bearer ${API_TOKEN}" -H "Content-Type: application/json" \
  --data "{\"type\":\"A\",\"name\":\"${RECORD_NAME}\",\"content\":\"${CURRENT_IP}\",\"ttl\":300,\"proxied\":false}" \
  > /dev/null
EOF
sudo chmod +x /opt/ddns/cloudflare-ddns.sh
```

Get `ZONE_ID` from the Cloudflare dashboard's domain overview (right sidebar).
Create `API_TOKEN` under Cloudflare → My Profile → API Tokens → "Edit zone
DNS" template, scoped to `gamenightbymike.com` only.

Run every 5 minutes:

```bash
( crontab -l 2>/dev/null; echo "*/5 * * * * /opt/ddns/cloudflare-ddns.sh" ) | crontab -
```

## ============= Step 4. Install Java on oscar

```bash
sudo apt update
sudo apt install -y openjdk-21-jre-headless
java -version
```

(Use the Java version each server's Minecraft release actually requires —
21 covers current Paper/vanilla releases as of 2026; older realms may need
Java 17.)

## ============= Step 5. Lay out the realm folders

```bash
sudo mkdir -p /opt/mc/{proxy,gatorland,river,gravestones}
sudo chown -R mike:mike /opt/mc
```

## ============= Step 6. Set up each backend server

Repeat per realm (example: gatorland, port 25566). Drop in the server jar
(Paper build from https://papermc.io/downloads for that realm's MC version),
then:

```bash
cd /opt/mc/gatorland
echo "eula=true" > eula.txt
```

Edit `server.properties`:

```properties
server-port=25566
server-ip=127.0.0.1
online-mode=true
enable-rcon=false
```

`server-ip=127.0.0.1` is what keeps this backend unreachable except through
Velocity. Give `river` port `25567`, `gravestones` port `25568`, and so on for
future realms.

systemd unit (`/etc/systemd/system/mc-gatorland.service`):

```ini
[Unit]
Description=Minecraft realm - gatorland
After=network.target

[Service]
User=mike
WorkingDirectory=/opt/mc/gatorland
ExecStart=/usr/bin/java -Xms2G -Xmx4G -jar paper.jar --nogui
Restart=on-failure
RestartSec=10
StandardInput=null

[Install]
WantedBy=multi-user.target
```

Repeat with `mc-river.service`, `mc-gravestones.service`, one file each,
pointing at their own `WorkingDirectory` and jar.

## ============= Step 7. Install and configure Velocity

```bash
cd /opt/mc/proxy
curl -o velocity.jar -L https://api.papermc.io/v2/projects/velocity/versions/3.4.0/builds/latest/downloads/velocity-3.4.0.jar
java -jar velocity.jar   # first run generates velocity.toml + forwarding.secret, then Ctrl+C
```

Edit `/opt/mc/proxy/velocity.toml`:

```toml
bind = "0.0.0.0:25565"
motd = "<green>Game Night by Mike</green>"
show-max-players = 50
online-mode = true

[servers]
gatorland = "127.0.0.1:25566"
river = "127.0.0.1:25567"
gravestones = "127.0.0.1:25568"
try = ["gatorland"]   # fallback if a player connects to something with no forced-host match

[forced-hosts]
"gatorland.gamenightbymike.com" = ["gatorland"]
"river.gamenightbymike.com" = ["river"]
"gravestones.gamenightbymike.com" = ["gravestones"]

[advanced]
compression-threshold = 256
```

On each backend server, install the Velocity-forwarding plugin/paper config
so the backend trusts the proxy for player identity: in each realm's
`config/paper-global.yml` (Paper 1.19.3+), set:

```yaml
proxies:
  velocity:
    enabled: true
    online-mode: true
    secret: "<contents of /opt/mc/proxy/forwarding.secret>"
```

systemd unit (`/etc/systemd/system/mc-proxy.service`):

```ini
[Unit]
Description=Velocity proxy - gamenightbymike.com
After=network.target

[Service]
User=mike
WorkingDirectory=/opt/mc/proxy
ExecStart=/usr/bin/java -Xms512M -Xmx1G -jar velocity.jar
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## ============= Step 8. Firewall

```bash
sudo ufw allow 22/tcp
sudo ufw allow 25565/tcp
sudo ufw enable
sudo ufw status
```

Backend ports (25566-2556x) are **not** opened — they're only reachable via
`127.0.0.1`, i.e. only from Velocity on the same box.

## ============= Step 9. Start everything

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mc-gatorland mc-river mc-gravestones mc-proxy
sudo systemctl status mc-proxy
```

## ============= Step 10. Test

1. From a machine outside your LAN (phone on cellular data works), add server
   `gatorland.gamenightbymike.com` in the Minecraft client with **no port**.
2. Confirm it lands you on the gatorland world, not a different realm.
3. Repeat for `river` and `gravestones`.
4. Kill your home internet's IP address in the router (or wait for the ISP to
   rotate it) and confirm the DDNS cron job updates Cloudflare within 5
   minutes and the server is reachable again.

## ============= Adding a new realm later

1. `mkdir /opt/mc/<realm>`, drop in the jar, `eula=true`, set
   `server-port=2556x` (next free port), `server-ip=127.0.0.1`.
2. New systemd unit `mc-<realm>.service`, copy Step 6's template.
3. Add one line to `[servers]` and one to `[forced-hosts]` in
   `velocity.toml`, then `sudo systemctl restart mc-proxy`.
4. One Cloudflare CNAME: `<realm>` → `mc.gamenightbymike.com`.

No router changes, ever.

## ============= Modded realm exception

If a realm needs Forge/NeoForge with server-required mods, Velocity can't
proxy its handshake. Give that one realm its own path instead:

1. Pick a dedicated port (e.g. `25570`), bind it to `0.0.0.0` (not
   `127.0.0.1`, since it bypasses the proxy).
2. Router: forward that one extra port to oscar.
3. Cloudflare: add an `SRV` record so the client still doesn't need to type
   the port:
   - Type: `SRV`, Service: `_minecraft`, Protocol: `_tcp`,
     Name: `<realm>` (Cloudflare will render it as
     `_minecraft._tcp.<realm>.gamenightbymike.com`),
     Priority `0`, Weight `5`, Port `25570`,
     Target: `mc.gamenightbymike.com`.
4. Modern Minecraft Java clients resolve SRV automatically, so players still
   just type `<realm>.gamenightbymike.com`.

This is the one case where you're back to "one port-forward per server," so
prefer Paper/Fabric-with-proxy-compatible-mods for anything that can live
through Velocity instead.
