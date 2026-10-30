# Play or test a realm from inside the house (hosts file override)

**Automation status:** None by nature. It's a per-PC override, not a change
to any shared system. `realm provision`/`activate` print the line to add. Full background and the SRV
explanation live in
[oscar-realm-hosting.md](../architecture/oscar-realm-hosting.md#testing-a-forced-host-from-inside-the-lan-without-a-phone);
this is the condensed how-to.

## When to use

**Every new realm, on every Windows PC in the house that plays on it.**
Without the hosts line, a PC at home reaches the realm through the router's
public IP (`69.237.13.77`), and the AT&T gateway handles that loop-back
unreliably. Seen with `hardcore` on 2026-10-30:

- The **first** join worked. Velocity logged the player as coming from
  `192.168.1.254`, the gateway, which shows the connection went through
  the loop-back.
- After leaving, every rejoin failed with **`Failed to connect to the
  server` / `Connection timed out: getsockopt`**.
- Velocity logged **nothing** for the failed attempts, and
  `Test-NetConnection <realm>.gamenightbymike.com -Port 25565` could still
  succeed. The gateway is flaky, not closed.
- Adding the hosts line fixed it.

`realm provision` and `realm activate` print the exact line for the new
realm in their handoff output. Players outside the house don't need it.
Consoles can't edit a hosts file, so at home they connect by LAN IP where
the game allows it (see
[bedrock-player-guide.md](bedrock-player-guide.md)).

Also use it when you want to confirm a realm's `[forced-hosts]` entry routes correctly
*before* relying on it from outside the LAN — after
[adding a CNAME](modify-cloudflare-cname.md), after
[changing a port](change-port.md), or after any `velocity.toml` edit — but
don't have a phone on cellular handy, and a raw LAN-IP connection or the
real domain typed from inside the house won't reach it (most home routers,
AT&T's included, can't hairpin a LAN client back out to the router's own
public IP).

## Steps

On the Windows dev box, open Notepad **as Administrator** and edit:

```
C:\Windows\System32\drivers\etc\hosts
```

Add one line per realm you want to test, pointing at oscar's **LAN** IP
(not the public one):

```
192.168.1.113 <realm_id>.gamenightbymike.com
```

Multiple realm hostnames can point at the same oscar LAN IP without
conflicting — each still sends its own distinct hostname in the Minecraft
handshake, so Velocity's `[forced-hosts]` still routes each to the right
backend.

In the Minecraft client, add the server as `<realm_id>.gamenightbymike.com`
— **no port**. See
[oscar-realm-hosting.md](../architecture/oscar-realm-hosting.md#testing-a-forced-host-from-inside-the-lan-without-a-phone)
for why no port is needed even through a hosts override (short version: no
SRV record exists for Velocity-fronted realms, so the client falls back to
the default port `25565`, and Velocity itself does the internal routing to
the realm's real backend port from there).

## Verify

Connecting lands you on the expected realm's world, not whatever `try`
falls back to in `velocity.toml`.

## Clean up

For a PC that stays at home, keep the lines. They're how it plays. For a
laptop leaving the house, or after a one-off test, remove (or `#`-comment)
the added lines, so the hostname resolves
through real DNS again — leaving a stale hosts entry means this dev box
specifically will keep hitting oscar's LAN IP even after its public IP or
DNS changes, which can be a confusing thing to debug weeks later.
