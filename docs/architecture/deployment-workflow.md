# docs/architecture/deployment-workflow.md

How changes made on the Windows dev box reach the live realms on `oscar`.

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

## Rolling back

- **Code/config problem** (bad `servers.json` entry, broken script): fix it
  in git — `git revert`/`git checkout` inside `/srv/minecraft` — then repeat
  step 7. Nothing here touches world data.
- **World data problem**: restore the affected realm's data directory from
  the most recent archive in `backups_root`, verified against its
  `.sha256` file, then restart that realm's service. This is unrelated to
  git and never requires touching `/srv/minecraft`.
