# Prism Launcher — family user guide

A plain-language guide for downloading, installing, and using
[Prism Launcher](https://prismlauncher.org) to play on our realms. This
isn't a `minecraftmgr` admin doc like the others in this folder — there's
nothing to run, no CLI, no accounts on oscar. It's for anyone in the family
who wants an easier way to launch Minecraft and jump into a specific realm
without fiddling with version numbers every time.

## Why Prism instead of the regular Minecraft launcher

The stock Minecraft launcher makes you manually switch versions every time
you want to play a different realm, and it mixes everyone's mods, worlds,
and settings together in one folder. Prism fixes both:

- **Instances.** Each "instance" is its own self-contained copy of a
  Minecraft version, with its own mods, settings, screenshots folder, and
  saved server list. Nothing from one instance leaks into another.
- **One-click launch.** Open Prism, double-click an instance, and it starts
  that exact version — no manual switching.
- **Saved servers.** Once you've added a realm's address to an instance,
  it's saved there for next time. Launch the instance, double-click the
  realm in the multiplayer list, you're in.
- **Works everywhere.** Windows, macOS, and Linux all use the same app and
  the same instance concept.

## 1. Download and install

Go to **[prismlauncher.org/download](https://prismlauncher.org/download)**
and pick your operating system:

- **Windows** — download the installer (`.msi`) and run it. Accept the
  defaults; there's nothing here to configure.
- **macOS** — download the `.dmg`, open it, drag Prism into Applications.
- **Linux** — easiest is Flatpak: search "Prism Launcher" in your
  distro's app store (GNOME Software, Discover, etc.), or from a terminal:
  `flatpak install flathub org.prismlauncher.PrismLauncher`.

Open Prism once it's installed. You'll land on an empty instance list —
that's expected, nothing to add yet.

## 2. Add your Minecraft account

Minecraft accounts are Microsoft accounts now — the same email/password you
already use to buy and play the game normally.

1. In Prism, click **Accounts** (top toolbar) → **Manage Accounts**.
2. Click **Add**.
3. A Microsoft sign-in window opens — log in the same way you would on
   minecraft.net.
4. Once it finishes, your account appears in the list with a checkmark next
   to it (that checkmark means it's the *active* account — the one Prism
   will launch the game as).

## 3. Create an instance for each Minecraft version you need

This is the one Prism-specific concept worth understanding: **one instance
per Minecraft version**, not one instance per realm. Several of our realms
share the same version, so they share an instance's saved-server list too.

Check **[minecraft.gamenightbymike.com](https://minecraft.gamenightbymike.com)**
for the current, up-to-date list of realms and the exact version each one
needs — that page is always the source of truth, and versions do change
over time as realms get upgraded. As of this writing:

| Realm | Version | Instance to use |
|---|---|---|
| Arbor | 1.21.10 | its own instance |
| Cave | 1.21.1 | shared instance |
| Poop | 1.21.1 | shared instance |
| River | 1.21.1 | shared instance |
| Gravestone | 26.1.2 | its own instance |

So in practice, today that's **three instances total** — one for 1.21.10,
one for 1.21.1 (covers Cave, Poop, and River), one for 26.1.2 — not five.

To create one:

1. Click **Add Instance** (or the **+** button) in Prism.
2. Give it a name you'll recognize, e.g. `1.21.1 - Cave, Poop, River`.
3. Under version, pick the Minecraft version from the table above.
4. Click **OK**/**Create**. It'll download that version — this only
   happens once per instance.

Repeat for each version you need.

## 4. Join a realm

The first time, this works exactly like it always has — Prism doesn't
change how you connect, it just launches the right version for you:

1. Double-click the instance for the version you need (see the table
   above).
2. Once the game window opens, go to **Multiplayer** → **Add Server**.
3. Get the realm's address from the
   [picker page](https://minecraft.gamenightbymike.com) — click **Copy**
   on that realm's card — and paste it in. Leave the port blank.
4. Click **Done**, then double-click the server to join.

**Every time after that**, it's genuinely one click: launch the instance,
the server you added is already sitting in the multiplayer list, double
click it. If that instance covers multiple realms sharing a version (like
Cave/Poop/River), add all of them the first time and you'll have all three
saved side by side.

## 5. Multiple Minecraft accounts

If more than one person in the family shares a computer, or someone has
their own separate Microsoft/Xbox account, Prism handles that without
needing a second install.

**Adding another account:**

1. **Accounts** → **Manage Accounts** → **Add**.
2. Sign in with the other Microsoft account.
3. Both accounts now show up in the list.

**Switching which account launches the game:**

- Quick way: **Accounts** menu → click the account you want active (the
  checkmark moves to it). The next instance you launch uses that account.
- Per-instance way: right-click an instance → **Edit Instance** → look for
  **Account Override** (or similarly named settings tab depending on
  Prism's version) and pin a specific account to that instance permanently.
  Handy if, say, one kid always uses one instance and you don't want to
  remember to switch accounts first.

## Troubleshooting

- **"Outdated server" / "Outdated client" / can't connect at all** — almost
  always a version mismatch. Double-check the realm's current version on
  the [picker page](https://minecraft.gamenightbymike.com) against the
  instance you're launching from; realm versions do change over time.
- **Connection times out** — the realm itself might not be running. Check
  its status on the picker page and use the **Autostart** button if it
  shows stopped.
- **Can't remember a realm's address** — always the
  [picker page](https://minecraft.gamenightbymike.com), never something to
  memorize. Click **Copy** on the realm's card.
- **Signed into the wrong account** — see the "Switching which account
  launches the game" section above.

## Automation status

None — this is a manual, one-time-per-person setup with no `minecraftmgr`
involvement. Nothing here reads from or writes to `servers.json`; the
version table above is a snapshot, not something generated by this repo's
tooling, so re-check the picker page if it's been a while since you set
your instances up.
