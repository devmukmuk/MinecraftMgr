# Add or change a realm's Cloudflare CNAME

**Automation status:** None, and not planned as a near-term automation
target — no Cloudflare API token exists anywhere on oscar (confirmed while
designing [PROV](../epics/PROV-design.md)), so this stays a dashboard-only
step unless that changes.

See [oscar-realm-hosting.md](../architecture/oscar-realm-hosting.md)'s
"Step 3: Cloudflare DNS" and "Adding a new realm later" sections for the
full architecture context (why one `A` record + per-realm `CNAME`s, why DNS
must stay grey-cloud/unproxied). This doc is just the distilled steps.

## When to use

- A brand-new realm needs its subdomain to exist at all (part of
  [provisioning](../epics/PROV-design.md), not covered by `realm provision`
  itself — it prints the reminder, doesn't do this step).
- A realm's `server_id` changed (i.e. you [deleted and re-added it](delete-realm.md)
  under a new id) and the old subdomain needs to point somewhere sane or be
  removed.

## Steps

1. Log into the Cloudflare dashboard for `gamenightbymike.com`.
2. DNS → Records → **Add record**:
   - Type: `CNAME`
   - Name: `<realm_id>` (becomes `<realm_id>.gamenightbymike.com`)
   - Target: `mc.gamenightbymike.com`
   - Proxy status: **DNS only** (grey cloud) — Minecraft's protocol isn't
     HTTP/TLS, Cloudflare's proxy can't forward it. An orange-clouded record
     here is the single most common way this breaks silently (connects,
     then times out).
3. Save.

To **remove** a realm's subdomain (see [delete-realm.md](delete-realm.md)):
find the `CNAME` record with that name and delete it from the same screen.

## Verify

```bash
nslookup <realm_id>.gamenightbymike.com
```

Should resolve to the same IP as `mc.gamenightbymike.com`. Then confirm a
real connection: add `<realm_id>.gamenightbymike.com` (no port) as a server
in the Minecraft client from a network outside your LAN (phone on cellular
is the reliable way to test this — see
[change-port.md](change-port.md) and
[modify-local-hosts-override.md](modify-local-hosts-override.md) for why
testing from inside the LAN needs a different approach).

## Gotchas

- DNS propagation/caching can lag a few minutes even with Cloudflare's
  normally-fast updates — and your own router/ISP resolver can hold a
  *negative* (NXDOMAIN) cache from before the record existed for longer
  than that. `ipconfig /flushdns` only clears the Windows-level cache, not
  the router's — if a brand-new subdomain doesn't resolve yet, try from a
  device on a different network (phone on cellular) before assuming
  something's actually wrong.
