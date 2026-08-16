# Test a realm's forced-host from inside the LAN (hosts file override)

**Automation status:** None by nature — this is a dev-box-local override for
testing, not a change to any shared system. Full background and the SRV
explanation live in
[oscar-realm-hosting.md](../architecture/oscar-realm-hosting.md#testing-a-forced-host-from-inside-the-lan-without-a-phone);
this is the condensed how-to.

## When to use

You want to confirm a realm's `[forced-hosts]` entry routes correctly
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

Remove (or `#`-comment) the added lines once done, so the hostname resolves
through real DNS again — leaving a stale hosts entry means this dev box
specifically will keep hitting oscar's LAN IP even after its public IP or
DNS changes, which can be a confusing thing to debug weeks later.
