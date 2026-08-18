# docs/workflows/

Runbooks for changing an **already-active** realm on oscar. `docs/epics/PROV-design.md`
covers *creating* a realm (`realm provision`/`realm activate`); everything here
picks up after that, once a realm is registered, wired into Velocity, and
players are on it. See [PAPER.md](../PAPER.md) for what Paper actually is
(not vanilla) and the three jar-lifecycle workflows — getting a jar,
deploying one, upgrading one — which that doc covers in one place instead
of scattering across here.

Each doc follows the same shape: when to use it, the steps, how to verify it
worked, and an **automation status** line. Where a manual step has a
follow-up command already proposed (not yet built), it links to
[PROV-design.md](../epics/PROV-design.md)'s "Future work" section rather than
repeating the proposal here.

## Why realm config files (`server.properties`, `whitelist.json`, `ops.json`,
`start.sh`, ...) aren't in git

This is deliberate, not an oversight — see
[deployment-workflow.md](../architecture/deployment-workflow.md)'s "Two
separate trees on oscar" section. `/srv/minecraft` (this repo's checkout) and
`<data_root>` (`/opt/mc`, each realm's live folder) are kept strictly apart:
no world data, and nothing that lives *alongside* world data, ever goes into
git. The reasons carry over to the config files directly:

- They're **per-realm instance data**, not shared code — `server.properties`
  for `gatorland` has no meaningful relationship to `river`'s, the way two
  files in `src/` do. There's nothing to diff/merge/review across realms.
- They **change on their own**, outside any deploy: `ops.json`/`whitelist.json`
  get rewritten by Minecraft itself the moment someone runs `/op` or
  `whitelist add` in-game, `usercache.json` on every player join. A git-tracked
  copy would drift from the live file within minutes of a deploy and turn
  every `git status` on oscar into noise.
- They're **already captured**, just not by git: `minecraftmgr backup run`
  (see [backup-realm.md](backup-realm.md)) tars up a realm's entire data
  directory — jar, `start.sh`, `server.properties`, every control file,
  `world/` — with a `.sha256` alongside it. That's the actual source of
  truth for "what was this realm's config at time T", and it already exists;
  git tracking the same files a second time would just be a worse version of
  the same thing.

`servers.json` (the registry — display name, port, version, status) is the
one thing about a realm that *is* git-tracked, and that's a deliberate
different case: it's small, hand-authored, shared reference data (the
realm-picker site and the trigger daemon both read it), not
instance/runtime state, and only the dev box can write it since oscar's
checkout can't push.

## The workflows

| Workflow | Automation today | Notes |
|---|---|---|
| [Change a realm's name](change-name.md) | Full — one command | |
| [Change a realm's port](change-port.md) | None | Touches 3 files across 2 machines |
| [Stop / restart a realm](stop-restart-server.md) | Full — `realm start`/`realm stop` (2026-08-18) | Not yet redeployed to oscar in place of the old `start_all`/`stop_all` scripts |
| [Back up a realm](backup-realm.md) | Full — one command | |
| [Restore a realm from backup](restore-from-backup.md) | None | |
| [Update a realm's jar version](update-jar-version.md) | None | |
| [Add/change a Cloudflare CNAME](modify-cloudflare-cname.md) | None | No API token on oscar |
| [Test with a local hosts override](modify-local-hosts-override.md) | None (by nature — dev-box-local) | |
| [Modify the whitelist](modify-whitelist.md) | None | Live console injection possible without a restart |
| [Modify server ops](modify-ops.md) | None | Live console injection possible without a restart |
| [Delete a realm completely](delete-realm.md) | None | Irreversible — read this one fully before running anything |
| [Convert vanilla/Fabric/Forge → Paper](convert-engine.md) | Deliberately manual/guided | One direction only — see that doc for why Paper → vanilla isn't a thing here |
| [Redeploy oscar's Minecraft scripts from git](redeploy-oscar-scripts.md) | None | One-time cutover, `sudo`/`minecraft`-user gated |

## For family members, not admins

One doc in this folder isn't an admin runbook at all —
[prism-user-guide.md](prism-user-guide.md) is a plain-language guide for
anyone in the family on downloading, installing, and using
[Prism Launcher](https://prismlauncher.org) to join our realms, including
handling multiple Minecraft accounts on one computer. No CLI, no oscar
access, nothing `minecraftmgr` touches.

## Automating these, one at a time

The plan is to pick these off individually rather than build a big change-realm
feature at once — same reasoning as `PROV`'s "Future work" section. Good
first candidates, roughly in order of how self-contained they are:

1. ~~**`realm stop <id>`**~~ — **done (2026-08-18)**, along with `realm start
   <id>`/`--all` for symmetry. Both are thin wrappers around
   `trigger_service.start_realm()`/`stop_realm()`, already written and
   tested. Superseded `tools/scripts/start_all_minecraft_servers.sh` and
   `stop_all_minecraft_servers.sh` — see
   [tools/scripts/README.md](../../tools/scripts/README.md).
2. **`realm console <id> "<command>"`** — the `send_console_command` primitive
   PROV-design.md already proposes. Unlocks whitelist/ops/gamerule changes
   live, with no restart, and is a small wrapper around the same
   `screen -X stuff` mechanism `stop_realm()` already uses.
3. **`realm audit-ports`** — read-only, no state mutation, but needs care
   since it has to scan real folders on oscar, not just `servers.json`.
4. Jar version update, port change — bigger, touch multiple files/machines,
   worth doing after the above land and prove out the pattern.
