# Change a realm's backend port

**Automation status:** None yet — proposed as future work in
[PROV-design.md](../epics/PROV-design.md#future-work-modifying-an-already-active-realm).

## When to use

A realm's backend port needs to move — usually to resolve a collision (two
real ones already found on oscar: `poop_1_21_1`/`poop_1_21_3` both on
`28314`, `arbor_1_21_10` reusing `gravestone`'s `26005` — see
[REG.md](../epics/REG.md)'s open work). Players never see this port; it's
purely the `127.0.0.1:<port>` Velocity forwards to, per
[oscar-realm-hosting.md](../architecture/oscar-realm-hosting.md).

Picking a new port: there's no automated uniqueness check yet (that's the
proposed `realm audit-ports` command). Manually cross-check both
`servers.json` and every realm's `server.properties` on oscar — the two real
collisions above came from realms that weren't even in `servers.json` yet, so
checking the registry alone isn't sufficient.

## Steps

Three files, two machines. Do them in this order so the realm is never
briefly using a port Velocity doesn't know about:

**1. On oscar, in the `minecraft` user's shell** (stop first — don't edit
`server.properties` while the process is running, it won't pick up a
mid-session change anyway):

```bash
sudo -iu minecraft
screen -r <data_dir>
# in-game console: stop
# wait for the screen session to exit back to shell, then Ctrl+A d if it doesn't
```

Edit `/opt/mc/<data_dir>/server.properties`, change `server-port=<old>` to
`server-port=<new>`.

Edit `/opt/mc/<data_dir>/start.sh` — the `PORT=` line the template renders
(see `tools/templates/start.sh.template`) — to the same new port.

Start it back up to confirm it comes up clean on the new port:

```bash
screen -dmS <data_dir> ./start.sh
screen -r <data_dir>
# confirm no bind-error in the log, Ctrl+A d to detach once it's up
```

**2. On the dev box**, update the registry and regenerate the site:

```bash
python -m minecraftmgr server update <server_id> --port <new>
python -m minecraftmgr web build --out public/index.html
git add servers.json public/index.html
git commit -m "docs(REG): move <server_id> to port <new>"
git push
```

**3. Back on oscar**, as `mike` (no `minecraft` boundary needed — `/opt/mc/_proxy/`
is `mike`-writable):

```bash
nano /opt/mc/_proxy/velocity.toml
# update the [servers] line for this realm to 127.0.0.1:<new>
```

Then, back in the `minecraft` user's shell, restart Velocity so it picks up
the new port:

```bash
sudo -iu minecraft
screen -S velocity_proxy -X quit
cd /opt/mc/_proxy
screen -dmS velocity_proxy java -Xms512M -Xmx1G -jar velocity.jar
```

## Verify

- `screen -ls` on oscar shows both the realm's session and `velocity_proxy`
  up.
- Connect to `<realm>.gamenightbymike.com` (no port) and confirm you land on
  the right world — this exercises the whole `[forced-hosts]` → `[servers]`
  → new port chain, not just that the process is alive.

## Gotchas

- Don't skip the "start it back up to confirm it binds" check in step 1 —
  if the new port collides with something else already listening on oscar,
  you want to find that out before touching `velocity.toml`, not after
  players report they can't connect.
- If you forget step 3's restart, players briefly get a "can't connect to
  server" from Velocity even though the realm itself is healthy — Velocity
  only reads `velocity.toml` at startup.
