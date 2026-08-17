# Client-side mods with our Paper realms

**Short answer: yes, you can run Fabric or Forge on your own client and
still connect to our realms — as long as the mods you install are
client-only.** Anything that requires the *server* to understand new
content (blocks, items, mechanics, networking) won't work, because every
realm behind Velocity is [Paper](PAPER.md), not Fabric or Forge, and
nothing in this project's tooling changes that. This doc is about your
personal game client, not anything `minecraftmgr` provisions or manages —
there's no server-side setup involved either way.

## Why this works at all

The Minecraft Java Edition network protocol itself doesn't care what mod
loader your client runs. Fabric and Forge don't replace that protocol —
they let mods add *extra* packets/behavior on top of it. A mod that never
sends anything the server doesn't already understand is invisible to the
server; the connection looks like a stock vanilla client the whole time.
That's the category BetterF3 (the F3-customization mod) and most
"quality of life" mods fall into — they only touch what's
rendered/processed locally.

This is also why [PAPER.md](PAPER.md)'s Paper-vs-vanilla distinction and
Velocity's "modern forwarding" protocol are irrelevant to this question in
the other direction: forwarding is a proxy↔backend concern (Velocity
proving your real identity to the Paper server behind it), not a
client↔proxy one. Velocity doesn't inspect or care whether the connecting
client is vanilla, Fabric, or Forge — it only ever cares what the
*backend* server speaks, which is a separate question already answered
by [oscar-realm-hosting.md](architecture/oscar-realm-hosting.md).

## Things that work fine

Client-only mods that just change what you see or how you interact,
without adding anything the server would need to know about:

- **HUD/overlay tools** — BetterF3 (customize the debug screen), minimaps
  (Xaero's), waypoints, coordinate/compass overlays.
- **Rendering** — shaders (Iris/Oculus + a shaderpack), Sodium and other
  performance mods, zoom mods, better fonts/UI mods.
- **Convenience** — freecam, no-chat-reports, cape/skin mods, better
  inventory sorting, tooltip mods.

These install and run entirely on your machine. No coordination with the
realm, no server-side install, no need to tell anyone you're using them —
same as running any client mod against a public Paper server you don't
administer.

## Things that won't work

Anything that needs the *server* to also run the mod:

- New blocks, items, entities, or recipes — the server has no registry
  entry for them. At best the added content silently does nothing; at
  worst the client desyncs or crashes on use.
- Mods that open custom network channels expecting a matching server-side
  handler (many tech mods, some magic mods, anything with its own GUI/data
  synced from the server).
- Anything that depends on server-side mechanics changes (custom world
  gen, modified game rules beyond vanilla's `/gamerule` set, etc.).

If a mod you want genuinely needs server support, converting one of our
realms to run it isn't on the table the way it might be for other
projects — see the next section.

## The Forge handshake caveat

Modern Forge (1.13+) detects when it's connecting to a non-Forge server
and can fall back to a "vanilla connection," disabling mod-added content
for that session rather than refusing to connect outright. In practice
this works for a Forge client with only client-side-safe mods installed,
but it's version- and mod-dependent — some mods force a hard requirement
and will block the connection entirely rather than degrading gracefully.
Fabric doesn't have an equivalent heavyweight handshake at all, so a
Fabric client is generally the lower-friction choice if you specifically
want mod-loader features (shaders via Iris, etc.) against our realms.

If Forge refuses to connect or a mod complains loudly on join, that's the
handshake rejecting itself, not a sign anything is wrong with the realm.

## If you actually need a modded server

This project has converted realms *away* from Fabric/Forge and onto
Paper on purpose — see [convert-engine.md](workflows/convert-engine.md) —
because Velocity's forwarding protocol doesn't exist for Fabric/Forge
backends, and dropping mods server-side was an accepted tradeoff for
getting on the shared proxy. That's a one-way, deliberate decision per
realm, not something this doc reverses.

If a realm's whole point genuinely requires server-required mods, the
existing pattern is to take that one realm off Velocity entirely and give
it its own dedicated port + Cloudflare `SRV` record — see
[oscar-realm-hosting.md](architecture/oscar-realm-hosting.md#modded-realm-exception)'s
"Modded realm exception." That's a server-side, admin-only change though,
not something you can get by just installing mods on your own client.

## One honesty note

Realms here are small/private (family and friends), so this isn't written
out of anti-cheat paranoia — but worth saying plainly: mods that give a
gameplay advantage (x-ray, reach/fly hacks framed as "utility") are a
different category from the QoL mods above, even though both are
technically "client-only" in the sense this doc otherwise uses. Use your
judgment the way you would on anyone else's server.
