# Redeploy oscar's Minecraft scripts from git

**Automation status:** None — manual, and partly `sudo`/`minecraft`-user
gated, so this can't be run non-interactively by the Claude Code SSH key
(see [[oscar_ssh_access]]). One-time cutover, not a recurring workflow.

## When to use

Once, after [tools/scripts/](../../tools/scripts/README.md) was imported into
git: to make oscar actually run the tracked copies instead of the untracked
originals at `/opt/mc/Scripts/` and `/opt/scripts/`. Run it again any time a
future PR changes something in `tools/scripts/` that a cron job or the
`config_ufw_rules.sh` runbook depends on.

**Do this after**, not instead of, going through
[tools/scripts/](../../tools/scripts/README.md)'s "known issues" column —
several of the imported scripts (`minecraft_single_backup.sh`'s stale
`BASE_DIR`, the hardcoded `servers=()` arrays) are known-broken against
oscar's current layout and shouldn't be cut over to blindly.

## Steps

1. **Pull the new files onto oscar** (no `sudo` needed — `/srv/mc` is
   `mike`-owned):

   ```bash
   ssh mike@oscar
   cd /srv/mc
   git pull
   ls tools/scripts/
   ```

2. **Compare against what's actually running**, one script at a time, before
   swapping anything:

   ```bash
   diff /srv/mc/tools/scripts/start_all_minecraft_servers.sh /opt/mc/Scripts/start_all_minecraft_servers.sh
   diff /srv/mc/tools/scripts/stop_all_minecraft_servers.sh  /opt/mc/Scripts/stop_all_minecraft_servers.sh
   diff /srv/mc/tools/scripts/config_ufw_rules.sh            /opt/mc/Scripts/config_ufw_rules.sh
   diff /srv/mc/tools/scripts/minecraft_all_in_one_backup_v1.sh /opt/mc/Scripts/minecraft_all_in_one_backup_v1.sh
   ```

   Only the provenance header comment at the top of each file should differ
   — if anything else differs, oscar's copy has drifted since the import and
   the diff needs to be understood before continuing.

3. **Point the cron entries at the new location.** The backup script's cron
   line runs as the `minecraft` user, which this SSH key cannot reach
   non-interactively — do this part yourself:

   ```bash
   sudo -iu minecraft
   crontab -l   # find the line invoking minecraft_all_in_one_backup_v1.sh (or minecraft_single_backup.sh)
   crontab -e   # change the path from /opt/mc/Scripts/... or /opt/scripts/... to /srv/mc/tools/scripts/...
   exit
   ```

   If `start_all_minecraft_servers.sh` is invoked anywhere at boot (systemd
   unit, `rc.local`, a login script) rather than by hand, update that
   reference the same way.

4. **Confirm equivalent behavior** before removing anything:
   - Run the backup script manually from its new path
     (`/srv/mc/tools/scripts/minecraft_all_in_one_backup_v1.sh`) and confirm
     a new archive lands in `/mnt/backup/minecraft` the same as before.
   - Run `start_all_minecraft_servers.sh` / `stop_all_minecraft_servers.sh`
     from the new path against a non-critical realm (e.g. `jitterbug`,
     already flagged disposable — see [[oscar_migration_status]]) and
     confirm the same screen-session behavior as the old copy.

5. **Remove the old, now-superseded copies** — only after step 4 is
   confirmed:

   ```bash
   rm -rf /opt/mc/Scripts/
   rm /opt/scripts/minecraft_single_backup.sh \
      /opt/scripts/minecraft_all_in_one_backup_v1.sh \
      /opt/scripts/config_ufw_rules.sh
   ```

   Leave the rest of `/opt/scripts/` alone — it's a separate, already
   git-tracked personal repo unrelated to Minecraft (see
   [tools/scripts/README.md](../../tools/scripts/README.md#also-worth-knowing)).

## Verify

- `crontab -l` (as `minecraft`) shows `/srv/mc/tools/scripts/...` paths, not
  `/opt/mc/Scripts/...` or `/opt/scripts/...`.
- `/opt/mc/Scripts/` no longer exists; the Minecraft-specific files are gone
  from `/opt/scripts/`.
- The next scheduled backup run produces a normal archive (check
  `/mnt/backup/minecraft/logs/` for that night's log).

## Notes

This does **not** fix any of the known issues in
[tools/scripts/README.md](../../tools/scripts/README.md) (hardcoded realm
lists, stale paths, backup-script consolidation) — it only moves the
*current, as-is* behavior onto a path that future `git pull`s keep in sync.
Fixing those is separate, incremental work tracked in that same README.
