# Modify a realm's server operators (ops)

**Automation status:** None yet — same story as
[modify-whitelist.md](modify-whitelist.md): `op`/`deop` are already real
console commands, so this is covered by the same proposed
`realm console <id> "<command>"` wrapper in
[PROV-design.md](../epics/PROV-design.md#future-work-modifying-an-already-active-realm)
once it exists.

## When to use

Granting or revoking operator (admin) permissions for a player on a realm —
`/gamemode`, `/tp`, and other privileged commands in-game.

**Think twice before granting op.** An operator can do essentially anything
in-world, including things that bypass the whitelist and gamerule
protections other players rely on. Only grant it to someone you'd trust with
full admin access to that realm.

## Steps (preferred — live, no restart)

As the `minecraft` user on oscar:

```bash
sudo -iu minecraft
screen -r <data_dir>
```

```
op <player_name>
```

or to revoke:

```
deop <player_name>
```

Detach with `Ctrl+A d`. Takes effect immediately, no reload/restart needed.

## Steps (alternative — while stopped)

```bash
nano /opt/mc/<data_dir>/ops.json
```

Entries:

```json
[
  {"uuid": "...", "name": "player_name", "level": 4, "bypassesPlayerLimit": false}
]
```

`level` 4 is full operator; lower levels grant a subset of permissions — see
Minecraft's own `op-permission-level` documentation if you need anything
other than full op. As with whitelist, prefer the live `op`/`deop` console
commands over a manual edit unless the realm is already stopped for another
reason — Minecraft resolves the UUID for you and there's no risk of a
concurrent-rewrite clobbering a hand edit.

## Verify

- In-game: the player can (or can no longer) run operator commands.
- `cat /opt/mc/<data_dir>/ops.json` reflects the change.

## Gotchas

- Same overwrite risk as `whitelist.json` — don't hand-edit `ops.json` while
  the server is also running.
- Removing op from a player who's currently online doesn't retroactively
  undo anything they already did with those permissions (world edits,
  teleports, etc.) — it only stops further privileged commands.
