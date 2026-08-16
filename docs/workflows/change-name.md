# Change a realm's display name

**Automation status:** Full — one command, from the dev box, no restart needed.

## When to use

The realm's *display name* (what shows on the realm-picker page) needs to
change. This does **not** rename the realm's folder, `server_id`, or
Velocity hostname — those are treated as immutable (see
[REG.md](../epics/REG.md)'s "Storage shape" note); changing one of those is
effectively [deleting and re-adding the realm](delete-realm.md), not this
workflow.

## Steps

Run from the Windows dev box (this repo's checkout):

```bash
python -m minecraftmgr server update <server_id> --name "New Display Name"
python -m minecraftmgr web build --out public/index.html
git add servers.json public/index.html
git commit -m "docs(REG): rename <server_id> display name"
git push
```

Nothing on oscar needs to change — the running realm process never reads its
own display name, and `velocity.toml` keys on `server_id`, not the display
name.

## Verify

- `python -m minecraftmgr server list` shows the new name.
- The realm-picker page (Cloudflare Workers deploy, picks up the push
  automatically) shows the new name on its card.
