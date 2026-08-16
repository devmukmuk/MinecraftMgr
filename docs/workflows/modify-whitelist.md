# Modify a realm's whitelist

**Automation status:** None yet, but the fastest of this group to automate —
`whitelist add`/`whitelist remove`/`whitelist reload` are already real
Minecraft console commands, so a thin `realm console <id> "<command>"`
wrapper (the `send_console_command` primitive proposed in
[PROV-design.md](../epics/PROV-design.md#future-work-modifying-an-already-active-realm))
covers this with no restart required.

## When to use

Adding or removing a player from a realm's whitelist. Every realm behind
Velocity runs with backend `online-mode=false` — the proxy handles real
Mojang auth and forwards the player's real UUID via the "modern forwarding"
secret set up during
[provisioning](../epics/PROV-design.md#current-design)/`patch_velocity_trust`.
That means `whitelist.json` (keyed by UUID) still works correctly and
enforces against the player's real identity, not a proxy-spoofed one — this
only holds if that Velocity trust config is intact, which is why
`provision`/`activate` patch it as part of first boot.

## Steps (preferred — live, no restart)

As the `minecraft` user on oscar:

```bash
sudo -iu minecraft
screen -r <data_dir>
```

Type directly into the console:

```
whitelist add <player_name>
whitelist reload
```

(or `whitelist remove <player_name>`). Detach with `Ctrl+A d` — no restart
needed, the change is live immediately.

## Steps (alternative — while stopped)

If the realm is already stopped for another reason (e.g. mid
[jar update](update-jar-version.md)), edit the file directly instead of
starting it just for this:

```bash
nano /opt/mc/<data_dir>/whitelist.json
```

Entries look like:

```json
[
  {"uuid": "...", "name": "player_name"}
]
```

Getting a player's UUID for a manual edit (rather than letting the in-game
`whitelist add` command resolve it) requires a lookup against Mojang's API —
prefer the live console command above unless the realm is already down for
another reason.

## Verify

- In-game: the added player can join; a removed player is kicked (if online)
  or refused on next join.
- `cat /opt/mc/<data_dir>/whitelist.json` reflects the change.

## Gotchas

- `whitelist.json` gets rewritten by Minecraft itself on every `whitelist
  add`/`remove` — this is exactly why it's not git-tracked (see
  [docs/workflows/README.md](README.md#why-realm-config-files-serverproperties-whitelistjson-opsjson-startsh--arent-in-git)).
  If you edit it by hand while the server is also running, your edit can be
  silently overwritten the next time Minecraft rewrites it.
