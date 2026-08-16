# Restore a realm from backup

**Automation status:** None — no `minecraftmgr backup restore` command
exists. This is the documented manual procedure from
[deployment-workflow.md](../architecture/deployment-workflow.md)'s "Rolling
back" section, written out in full here.

## When to use

A realm's world data got corrupted, a bad edit broke it, or someone wants to
roll back to a known-good point — anything where the fix is "put back an
earlier archive" rather than "undo a config change" (that's a manual re-edit,
not a restore).

## Steps

As the `minecraft` user on oscar (this stops/starts the realm's process):

```bash
sudo -iu minecraft
```

1. **Stop the realm** first — see [stop-restart-server.md](stop-restart-server.md).
   Restoring into a directory a live process still has files open in will
   corrupt the restore.

2. **Verify the archive before trusting it:**

   ```bash
   cd <backups_root>
   sha256sum -c <server_id>-<timestamp>.tar.gz.sha256
   ```

   Don't skip this — restoring a truncated or corrupted archive is worse
   than not restoring at all, since it can silently replace a working (if
   imperfect) world with a broken one.

3. **Move the current directory aside rather than deleting it** — keep it as
   a fallback until the restore is confirmed good:

   ```bash
   mv /opt/mc/<data_dir> /opt/mc/<data_dir>.pre-restore
   ```

4. **Extract the archive:**

   ```bash
   tar -xzf <backups_root>/<server_id>-<timestamp>.tar.gz -C /opt/mc
   ```

   `backup_service.backup_server()` archives with `arcname=entry.server_id`,
   so the extracted top-level folder is named after the `server_id`, not
   necessarily `<data_dir>` if they ever diverge — check what actually landed
   (`ls /opt/mc/`) and rename it to match `<data_dir>` if needed before the
   next step.

5. **Start it back up** and confirm it comes up clean:

   ```bash
   cd /opt/mc/<data_dir>
   screen -dmS <data_dir> ./start.sh
   screen -r <data_dir>
   # watch the log for a clean boot, Ctrl+A d once confirmed
   ```

6. **Once confirmed good**, remove the `.pre-restore` copy to reclaim disk
   space:

   ```bash
   rm -rf /opt/mc/<data_dir>.pre-restore
   ```

## Verify

- The realm boots without errors and the world matches what you expected
  from that backup's timestamp.
- Connect and confirm in-game state (builds, inventory, etc.) matches.

## Gotchas

- This is unrelated to git and never touches `/srv/minecraft` —
  `servers.json` doesn't need any change for a restore, since the realm's
  identity (`server_id`, port, `data_dir`) doesn't change.
- If the restore turns out wrong, the `.pre-restore` copy from step 3 is
  the way back — don't skip that step to save a `mv`.
