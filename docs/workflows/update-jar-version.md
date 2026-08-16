# Update a realm's jar (Minecraft/Paper version)

> See [PAPER.md](../PAPER.md) for what Paper actually is (not vanilla — a
> different server implementation entirely) and where to get a verified
> build; this doc assumes you already have one.

**Automation status:** None — proposed as future work in
[PROV-design.md](../epics/PROV-design.md#future-work-modifying-an-already-active-realm).
`ensure_jar_cached()` (with its Paper-manifest validation) and `stop_realm()`
already exist and do the hard parts; there's just no command chaining them
into an update flow yet.

## When to use

A new Paper build or Minecraft version should come in place for an existing
world. This is an **in-place jar swap**, not a new world — the world save
itself is untouched, so this is safe to do repeatedly as Paper ships patch
builds.

## Prerequisites

- [Back up the realm first](backup-realm.md) — non-optional here, a jar
  swap is the one edit in this list that can genuinely break a world (a
  downgrade, or too large a version jump, can corrupt chunk data).
- The target version's jar must be Paper, checksum-verified, and in
  `_jarcache/`. Confirm with:

  ```bash
  cd /srv/minecraft
  python -m minecraftmgr realm inspect _jarcache/server_<version_with_underscores>.jar
  ```

  (or manually via `zipfile`/`unzip -p` + `META-INF/MANIFEST.MF`'s
  `Main-Class`, the same check `ensure_jar_cached(require_paper=True)`
  automates for `provision`). If it's not cached yet, download the right
  build from `fill.papermc.io` and verify its sha256 against the API
  response before dropping it into `_jarcache/`.

## Steps

As the `minecraft` user on oscar:

1. [Stop the realm](stop-restart-server.md).

2. Back up the *current* jar specifically, not just the whole realm (belt
   and suspenders alongside the full backup from prerequisites):

   ```bash
   cd /opt/mc/<data_dir>
   cp server_<data_dir>.jar server_<data_dir>.jar.bak
   ```

3. Copy in the new jar under the same filename `start.sh` expects
   (`server_<data_dir>.jar` — see `tools/templates/start.sh.template`):

   ```bash
   cp /opt/mc/_jarcache/server_<new_version_with_underscores>.jar server_<data_dir>.jar
   ```

4. Start it and watch the log for a clean boot — Paper prints its own
   version banner and (for a Minecraft version bump) a data-conversion
   pass on `world/` the first time it opens a world saved by an older
   version:

   ```bash
   screen -dmS <data_dir> ./start.sh
   screen -r <data_dir>
   ```

5. On the dev box, update the registry and regenerate the site:

   ```bash
   python -m minecraftmgr server update <server_id> --mc-version <new_version>
   python -m minecraftmgr web build --out public/index.html
   git add servers.json public/index.html
   git commit -m "docs(REG): bump <server_id> to <new_version>"
   git push
   ```

## Verify

- The log shows a clean `Done (` boot with no exceptions during world load.
- Connect and confirm the client-reported server version matches.
- Leave `server_<data_dir>.jar.bak` in place for a few days before deleting
  it, in case a delayed issue surfaces (a corrupted chunk that only loads
  when a player visits that area, for instance).

## Gotchas

- **Never downgrade** a Minecraft version against a world that's already
  been opened by a newer one — the data-format conversion isn't reversible.
  If you need to go back, restore from the backup taken in the
  prerequisites instead of copying the old jar back in.
- Skipping multiple major versions in one jump (e.g. 1.20 straight to 1.21.3)
  is riskier than doing it one release at a time — Paper's own upgrade notes
  for the target version are worth reading first, not just the jar.
