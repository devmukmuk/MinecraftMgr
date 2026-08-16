# Delete a realm completely

**Automation status:** None, and not a good near-term automation target —
this is the one workflow in this set that's genuinely destructive and
irreversible past a certain point. `minecraftmgr server remove` only touches
`servers.json`; it doesn't touch the filesystem, Velocity, or Cloudflare on
purpose (see [REG.md](../epics/REG.md)) — full teardown always needs the
manual steps below in addition.

**Read this whole doc before running anything.** The steps are ordered so
that every step before the last one is still recoverable if you change your
mind.

## When to use

A realm is being permanently retired — not just stopped
([stop-restart-server.md](stop-restart-server.md) if you just want it
offline but keep it around) and not just deregistered from the picker page
(`server remove` alone hides it from the site but leaves everything else
running and reachable by direct connection).

## Steps

**1. Take a final backup, and don't skip this even if you're sure.**

```bash
cd /srv/minecraft
python -m minecraftmgr backup run <server_id>
```

This is the only copy of the world that will exist once you're done — keep
the archive somewhere outside `backups_root` if you want a genuine
long-term-safe copy rather than something that could get pruned later.

**2. Stop the realm.** See [stop-restart-server.md](stop-restart-server.md).
Nothing after this point should be done while it's still running.

**3. Remove it from Velocity, then restart Velocity.**

As `mike` (no `minecraft` boundary needed for the edit itself):

```bash
nano /opt/mc/_proxy/velocity.toml
# delete this realm's line from [servers] and its line from [forced-hosts]
```

As `minecraft`, restart to apply:

```bash
sudo -iu minecraft
screen -S velocity_proxy -X quit
cd /opt/mc/_proxy
screen -dmS velocity_proxy java -Xms512M -Xmx1G -jar velocity.jar
```

Do this **before** deleting the Cloudflare CNAME below — otherwise there's a
window where the subdomain still resolves but Velocity has nowhere to send
it, which surfaces to players as a confusing "kicked, no reason given"
instead of a clean DNS failure.

**4. Remove the Cloudflare CNAME.** See
[modify-cloudflare-cname.md](modify-cloudflare-cname.md)'s "remove" note —
delete the `CNAME` record for this realm's subdomain.

**5. Deregister from `servers.json`**, from the dev box:

```bash
python -m minecraftmgr server remove <server_id> --yes
python -m minecraftmgr web build --out public/index.html
git add servers.json public/index.html
git commit -m "docs(REG): remove <server_id>"
git push
```

**6. Delete the data directory — the irreversible step.** Only after
confirming the backup from step 1 completed and its `.sha256` checksum
verifies:

```bash
sha256sum -c <backups_root>/<server_id>-<timestamp>.tar.gz.sha256
```

Then, as `minecraft` on oscar:

```bash
rm -rf /opt/mc/<data_dir>
```

Consider renaming instead of deleting if you're not fully certain
(`mv /opt/mc/<data_dir> /opt/mc/<data_dir>.deleted-<date>`) and coming back
to actually `rm -rf` it a week later once nobody's asked about it.

## Verify

- `screen -ls` on oscar no longer lists the realm.
- `/opt/mc/_proxy/velocity.toml` has no reference to it, and `velocity_proxy`
  restarted cleanly (`screen -r velocity_proxy`, check the log, detach).
- The realm-picker page no longer shows a card for it.
- `<realm>.gamenightbymike.com` fails to resolve (or resolves but the
  connection is refused, if Cloudflare's cache hasn't caught up yet).

## Gotchas

- Doing step 5 (`servers.json`) without steps 3–4 first leaves the realm
  fully reachable by anyone who already has the address bookmarked in their
  Minecraft client — it just stops showing on the picker page. Deregistering
  is not the same as taking it offline.
- This entire workflow assumes you actually want the realm gone. If the
  goal is just "stop it for now, maybe bring it back later," use
  [stop-restart-server.md](stop-restart-server.md) instead and stop reading
  here.
