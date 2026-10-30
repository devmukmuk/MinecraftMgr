# Upgrade the Velocity proxy

**Automation status:** None. Run by hand on oscar a few times a year.

**Current version:** Velocity **4.3.1 build 45** (STABLE). Upgraded from
4.0.0 on 2026-10-30, because 4.0.0 refused 26.3 clients. Proxy plugins:
Geyser 2.11.3-b1251 and Floodgate 2.2.5-SNAPSHOT b141 (see
[bedrock-crossplay.md](bedrock-crossplay.md)).

## When to use

- Players get **`Incompatible client! Please use 1.7.2-<version>`** when
  joining. That message comes from Velocity, not the realm: the proxy
  doesn't know the client's Minecraft version yet. This happens after a
  realm moves to a newer Minecraft than Velocity supports. On 2026-10-30,
  `hardcore` went to 26.3 while Velocity 4.0.0 stopped at 26.2.
- Before moving any realm to a new Minecraft version, check that Velocity
  supports it.

A newer Velocity still supports every older client version, so upgrading
it doesn't affect realms that stay on older versions.

## Steps

All as `mike` on oscar. Velocity runs as `minecraft` under
`velocity-proxy.service` from `/opt/mc/_proxy` (see
[tools/systemd/velocity-proxy.service](../../tools/systemd/velocity-proxy.service)).
It needs Java 25 (see
[oscar-migration-plan.md](../architecture/oscar-migration-plan.md)).

**1. Check the running version.** Use the last boot line, not the first.
The journal goes back weeks.

```bash
sudo journalctl -u velocity-proxy --no-pager | grep -i "booting up velocity" | tail -1
```

**2. Pick a build.** List the versions, then the newest builds of the latest
release and its snapshot:

```bash
curl -s https://fill.papermc.io/v3/projects/velocity | python3 -m json.tool | head -30

for V in 4.3.1 4.3.2-SNAPSHOT; do
  echo "== $V"
  curl -s "https://fill.papermc.io/v3/projects/velocity/versions/$V/builds" \
    | python3 -c "import json,sys
for b in json.load(sys.stdin)[:3]:
    d=b['downloads']['server:default']
    print(b['id'], b['channel'], b.get('time',''), d['url'], d['checksums']['sha256'])
    for c in b.get('commits',[])[:4]: print('   -', c.get('message','').splitlines()[0])"
done
```

Prefer the newest **STABLE** build. A `-SNAPSHOT` (BETA) build is fine if
only it supports the version you need. To check a build supports a
Minecraft version, look in its commits for that version or a later
snapshot. For example, 4.3.1's commits mention `26.4-snapshot-5`, so
26.3 is covered. A jump to a new **major** version (3.x to 4.x) can change
`velocity.toml` and break plugins. Read its release notes first.

**3. Download and verify.** Fill in the URL and sha256 from step 2.
`sha256sum -c` must print `OK`.

```bash
cd /tmp
curl -L -o velocity-new.jar "<download url>"
echo "<sha256>  velocity-new.jar" | sha256sum -c -
```

**4. Back up, swap, restart.** Do this when no one is playing, because the
restart disconnects everyone on every realm for a few seconds.

```bash
sudo -u minecraft cp -a /opt/mc/_proxy /opt/mc/_proxy.bak-$(date +%Y%m%d)
sudo -u minecraft cp /tmp/velocity-new.jar /opt/mc/_proxy/velocity.jar
sudo systemctl restart velocity-proxy
sleep 15
sudo journalctl -u velocity-proxy --since "2 min ago" --no-pager \
  | grep -i -E "booting up|done|error|exception|geyser|floodgate"
```

## Verify

- `Booting up Velocity <new version>...`, then `Done (...)!`.
- Geyser and Floodgate load (`Loaded plugin ...`, `Started Geyser on UDP
  port 19132`) with no exceptions.
- Join the realm on the new Minecraft version, and quickly join one realm
  on an older version.

**Expected, harmless:** a `NoClassDefFoundError` (for example
`com/velocitypowered/api/event/proxy/ListenerCloseEvent`) in the
**"Shutdown thread"** of the **old** process (the earlier PID in
`java[...]`). Its jar was replaced while it was running, so it can't load a
class during shutdown. Only errors from the new process's PID matter.

`read timed out` lines from unknown IPs are internet scanners hitting
port 25565, not part of the upgrade.

## Roll back

```bash
sudo systemctl stop velocity-proxy
sudo -u minecraft cp /opt/mc/_proxy.bak-<date>/velocity.jar /opt/mc/_proxy/velocity.jar
sudo systemctl start velocity-proxy
```

If the new version rewrote `velocity.toml` or plugin configs, restore the
whole folder from `_proxy.bak-<date>` instead. Delete old
`_proxy.bak-*` folders once the new version has run cleanly for a while.

## Plugins

Geyser logs a notice when a newer Bedrock version needs a Geyser update
(on 2026-10-30: Bedrock 26.60). Java players aren't affected. To update
Geyser or Floodgate, use the download URLs in
[bedrock-crossplay.md](bedrock-crossplay.md), then do the same backup and
restart as above.
