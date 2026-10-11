# Bedrock crossplay (Geyser + Floodgate)

**Automation status:** None. This is a one-time proxy setup plus a short
per-realm and per-player checklist, all done by hand. Set up and confirmed
working on 2026-10-11, when a Windows Bedrock client joined Blue through the proxy.

## When to use

- You want Bedrock players (Windows "Minecraft for Windows", Xbox, Switch,
  phones/tablets) to join the same realms as Java players.
- You're adding another realm to what Bedrock players can reach.
- You're whitelisting a new Bedrock player.
- A Bedrock player can't connect. See [Troubleshooting](#troubleshooting).

For the player's side (adding the server in the Bedrock app or using the
Switch), point them at [bedrock-player-guide.md](bedrock-player-guide.md).

## How it fits together

```
Bedrock client ──UDP 19132──► Geyser (on the Velocity proxy, /opt/mc/_proxy)
                                 │  translates Bedrock ⇄ Java protocol
                                 ▼
                              Floodgate (proxy)  ── Xbox sign-in, no Java account needed
                                 │  sends the player as ".Gamertag"
                                 ▼
                              Velocity ──► first realm in `try` ──/server <realm>──► other realms
                                                (each realm: floodgate plugin + the proxy's key.pem)
```

- **Geyser runs only on the proxy.** It must **not** be installed on a realm.
  A realm behind Velocity detects the proxy, logs "This server appears to be
  running behind a Velocity proxy! Remove the Geyser plugin from this
  server…", and disables Geyser-Spigot.
- **Floodgate** lets Bedrock players sign in with their Microsoft/Xbox
  account. It runs on the proxy, and on every realm that should see Bedrock
  players as proper Floodgate players (skins, `fwhitelist`). Every copy must
  share the **same `key.pem`**.
- Bedrock players appear in game with a `.` prefix (Floodgate's default
  `username-prefix`), e.g. `.SomeGamertag`, with a UUID of the form
  `00000000-0000-0000-000X-XXXXXXXXXXXX` (derived from their Xbox XUID).
- **Geyser speaks only the newest Java version.** A realm running an
  older version needs **ViaVersion**, or Bedrock players are refused when
  joining it. This matters most for the realm in Velocity's `try` list,
  since that's where every player lands first.

## One-time setup (the proxy)

As `minecraft` on oscar, unless noted otherwise.

1. **Install the proxy plugins:**

   ```bash
   cd /opt/mc/_proxy/plugins
   curl -L -o Geyser-Velocity.jar    https://download.geysermc.org/v2/projects/geyser/versions/latest/builds/latest/downloads/velocity
   curl -L -o floodgate-velocity.jar https://download.geysermc.org/v2/projects/floodgate/versions/latest/builds/latest/downloads/velocity
   ```

2. **Restart the proxy once** so both plugins write their config. This
   disconnects everyone on every realm for a moment:

   ```bash
   sudo systemctl restart velocity-proxy      # as mike (needs sudo)
   ```

3. **Configure them:**
   - `/opt/mc/_proxy/plugins/Geyser-Velocity/config.yml`: under `java:`, set
     `auth-type: floodgate`. The default `online` would require Bedrock
     players to also own a Java account. Leave `bedrock: port: 19132`.
   - `/opt/mc/_proxy/plugins/floodgate/config.yml`: set
     `send-floodgate-data: true`.

4. **Restart the proxy again**, then confirm Geyser is up:

   ```bash
   journalctl -u velocity-proxy -n 50 --no-pager | grep -i geyser
   # expect: "Started Geyser on UDP port 19132"
   ```

5. **Open the firewall on oscar.** Do this as `mike`, since `ufw` is system-wide
   and needs sudo; it isn't a `minecraft`-user job:

   ```bash
   sudo ufw allow 19132/udp comment 'Geyser Bedrock'
   ```

   Java's 25565/tcp is already allowed. Without this rule, Geyser answers
   on oscar itself but nothing on the LAN can reach it.

6. **Router (only for players outside the house):** forward **UDP 19132**
   to oscar (192.168.1.113). On an AT&T gateway this is under Firewall →
   NAT/Gaming → a custom service for UDP 19132 → 19132, assigned to oscar.
   LAN players don't need this. As of 2026-10-11 it hasn't been done.

## Per realm: making a realm reachable for Bedrock

As `minecraft`:

1. **Install Floodgate on the realm.** Use the Spigot/Paper build in
   `plugins/` (the same file Blue has), then restart the realm once so it
   creates `plugins/floodgate/`.
2. **Copy the proxy's key** over the realm's own generated one:

   ```bash
   cp /opt/mc/_proxy/plugins/floodgate/key.pem /opt/mc/<data_dir>/plugins/floodgate/key.pem
   ```

   A mismatched key means Bedrock players are rejected by that realm. Each
   Floodgate generates its own key on first start, so this step is always needed.
3. **If the realm's Minecraft version is older than Geyser's**, add
   ViaVersion. A single jar supports every server version, so you can copy it
   from a realm that already has it:

   ```bash
   cp /opt/mc/blue_26_2/plugins/ViaVersion-*.jar /opt/mc/<data_dir>/plugins/
   ```

   Gravestone (26.1.2, the `try` landing realm) needed this on 2026-10-11.
   Its log then shows `ViaVersion detected server version: 26.1-26.1.2`.
4. **Make sure Geyser-Spigot is not in the realm's `plugins/`.**
5. **Restart the realm cleanly** (`realm stop <id>`, wait, then `realm start <id>`;
   see [stop-restart-server.md](stop-restart-server.md)). Its log should
   show `[floodgate] Enabling floodgate …` with no key errors.

## Per player: whitelisting a Bedrock player

All realms run `enforce-whitelist=true`, so a Bedrock player must be
whitelisted **on every realm they'll enter**, including the `try` landing
realm, or they get "You are not whitelisted on this server!".

The normal `whitelist add <name>` can't resolve a `.Gamertag`, because that
isn't a Mojang account. `fwhitelist add <gamertag>` (Floodgate's
command) only works on realms that have Floodgate, and only once GeyserMC
knows the player. Before that, it fails with "Unable to find user in our
cache". The method that always works:

1. **Have the player connect once.** They'll be refused, but that's fine,
   because the attempt records their name and UUID in the proxy's log:

   ```bash
   journalctl -u velocity-proxy --since today --no-pager \
     | grep "Floodgate player who is logged in as"
   # … Floodgate player who is logged in as .SomeGamertag 00000000-0000-0000-000X-XXXXXXXXXXXX joined
   ```

2. **Append them to each realm's `whitelist.json`** (as `minecraft`, with
   the values from step 1):

   ```bash
   cd /opt/mc/<data_dir>
   cp whitelist.json whitelist.json.bak
   python3 - <<'EOF'
   import json
   UUID, NAME = "00000000-0000-0000-000X-XXXXXXXXXXXX", ".SomeGamertag"
   p = "whitelist.json"
   wl = json.load(open(p))
   if not any(e["uuid"] == UUID for e in wl):
       wl.append({"uuid": UUID, "name": NAME})
   json.dump(wl, open(p, "w"), indent=2)
   print([e["name"] for e in wl])
   EOF
   ```

3. **Load it without a restart:** in the realm console (`screen -r <data_dir>`),
   type `whitelist reload`, then detach with `Ctrl+A d`. Don't type `stop`.

The same person playing on Java and on Bedrock is **two whitelist entries**:
their Java name, and their `.Gamertag` with the `00000000-…` UUID. See also
[modify-whitelist.md](modify-whitelist.md).

## Verify

- **Proxy:** `systemctl status velocity-proxy` shows active, and
  `ss -uln | grep 19132` shows Geyser listening.
- **From another machine on the LAN:** a Bedrock "unconnected ping" to
  `192.168.1.113:19132` should come back with the MOTD (`MCPE;Game Night by
  Mike;…`). If it does from oscar itself but not from the LAN, it's the `ufw` rule.
- **Join:** the proxy log shows `[geyser] Player connected with username …`,
  then `[server connection] .<Gamertag> -> <realm> has connected`.
- **Realm log:** no Geyser-Spigot lines, and `[floodgate] Enabling …` with
  no key errors.

## Troubleshooting

Each of these was hit during the 2026-10-11 setup:

| Symptom | Cause | Fix |
|---|---|---|
| Realm log: "This server appears to be running behind a Velocity proxy! Remove the Geyser plugin…", then Geyser-Spigot disables itself | Geyser installed on the realm | Remove it from the realm; install Geyser-Velocity on the proxy |
| Bedrock client can't find or connect to the server on the LAN; ping from oscar works, from the LAN doesn't | `ufw` blocks UDP 19132 | `sudo ufw allow 19132/udp` (as `mike`) |
| Bedrock player kicked on joining the landing realm with a version error | Realm older than Geyser's Java version | ViaVersion on that realm (per-realm step 3) |
| "You are not whitelisted on this server!" | `.Gamertag` not in that realm's `whitelist.json` | Per-player steps above, on **each** realm they'll enter |
| `fwhitelist add` → "Unable to find user in our cache" | Player has never connected through Geyser, or the gamertag is wrong | Have them connect once, check the exact gamertag in the proxy log, or use the `whitelist.json` method |
| Bedrock players rejected by one realm only | That realm's `plugins/floodgate/key.pem` differs from the proxy's | Copy the proxy's `key.pem` in and restart the realm |
| Bedrock players asked for a Java login | Geyser `auth-type: online` | Set `auth-type: floodgate`, restart the proxy |

## Not done yet / ideas

- Router forward of UDP 19132 for outside Bedrock players.
- Sending Bedrock players straight to a realm by hostname: Geyser's
  `forward-hostname: true` plus a forced host (`blue.gamenightbymike.com`)
  would work like the Java forced hosts. It doesn't help on the LAN, where
  players connect by IP.
- Switch players outside the LAN: the Switch can't add custom servers, so
  it needs BedrockConnect or the MCXboxBroadcast Geyser extension. See the
  [player guide](bedrock-player-guide.md).
