# docs/architecture/deployment-workflow.md

How changes made on the Windows dev box reach the live realms on `oscar`.

> This describes the *target* state. For how oscar's real, pre-split
> `/srv/minecraft` layout gets migrated to this, see
> [oscar-migration-plan.md](oscar-migration-plan.md).

## Two separate trees on oscar

Keep these apart — don't let one grow into the other:

- **`/srv/minecraft`** — a checkout of this git repo (`devmukmuk/MinecraftMgr`).
  Scripts, `src/`, `tools/`, docs, and the tracked `servers.json` registry
  live here. No world data, ever.
- **`<data_root>` (default `/opt/mc`, see `minecraftmgr.yaml` on oscar)** —
  each realm's live server folder (jar, `server.properties`, the actual
  world save). Untracked, matches the layout in
  [oscar-realm-hosting.md](oscar-realm-hosting.md).

Earlier drafts of this workflow had world saves living inside the git tree
and used `git stash` before every pull to get them out of the way. That was
dropped: world saves are large, binary, and change on every autosave, so
tracking them in git would balloon the repo and make `stash`/`stash pop`
increasingly likely to conflict. Splitting the trees means a deploy is just
"pull, then restart" — no stash dance, and backups are independent tar/sha256
snapshots handled by `minecraftmgr backup`, not git.

## Scripts

`tools/scripts/` (oscar-side Minecraft automation — start/stop-all, backups,
firewall config) lives inside the git tree like everything else here, so it
rides this same pull-based flow with no special-casing. See
[tools/scripts/README.md](../../tools/scripts/README.md) for what's in there
and its current state, and
[redeploy-oscar-scripts.md](../workflows/redeploy-oscar-scripts.md) for the
one-time cutover from oscar's old untracked copies to this location.

## Deploy steps

1. Make changes locally in this repo (Windows dev box).
2. `git push` to `https://github.com/devmukmuk/MinecraftMgr.git`.
3. `ssh mike@oscar`
4. `cd /srv/minecraft`
5. `python -m minecraftmgr backup run --all` — snapshot every realm's data
   directory before touching anything, independent of git.
6. `git pull`
7. Restart whichever realms changed:
   `sudo systemctl restart mc-<realm>` (see
   [oscar-realm-hosting.md](oscar-realm-hosting.md) for the per-realm
   systemd units), or `mc-proxy` if `velocity.toml` changed.
8. **Restart `mc-trigger.service` if the change touches anything it
   imports** — `services/trigger_daemon.py`, `capacity_service.py`,
   `trigger_service.py`, `registry_service.py`, or anything those pull in.

### Why step 8 is easy to forget — and did get forgotten (2026-08-18)

`mc-trigger.service` is a long-running process (`ThreadingHTTPServer`,
started once by `minecraftmgr trigger serve` and left running). `git pull`
only updates the files on disk — a process that's already running keeps
executing whatever it already loaded into memory until it's explicitly
restarted. A CLI command (`minecraftmgr realm start <id>`) never hits this,
since every invocation is a fresh process that always imports current code
— only the *daemon* can go stale.

This actually happened: after merging the capacity-cap PR (#90) and
confirming it worked from the CLI, `mc-trigger.service` itself was never
restarted. The AUTOSTART button kept calling the **old**, pre-capacity-cap
`start_realm()` path with zero eviction logic, so repeated AUTOSTART clicks
on the picker page started 5 realms at once against a cap of 3 — while the
CLI, tested separately, enforced the cap correctly the whole time. Found by
comparing `realm status` output against a manual `screen -ls`, restarted
with `sudo systemctl restart mc-trigger.service`, confirmed fixed
immediately after.

**Rule of thumb**: any change to a service module reachable from
`trigger_daemon.py` needs `mc-trigger.service` restarted as part of the
same deploy that changed it — not "eventually," not "next time it's
convenient." Verify with `sudo systemctl status mc-trigger.service
--no-pager` — the `Active: active (running) since ...` timestamp should be
at or after the deploy that changed the code.

## Rolling back

- **Code/config problem** (bad `servers.json` entry, broken script): fix it
  in git — `git revert`/`git checkout` inside `/srv/minecraft` — then repeat
  step 7. Nothing here touches world data.
- **World data problem**: restore the affected realm's data directory from
  the most recent archive in `backups_root`, verified against its
  `.sha256` file, then restart that realm's service. This is unrelated to
  git and never requires touching `/srv/minecraft`.
