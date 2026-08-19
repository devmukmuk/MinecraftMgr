"""Render the exact copy-paste snippets needed to finish wiring a newly
provisioned/activated realm into servers.json, velocity.toml, and Cloudflare.

Pure text rendering, no I/O -- provision/activate never touch those files
themselves. servers.json can only be mutated from the dev box (oscar's
checkout can't push); velocity.toml can be edited on oscar without the
`minecraft` boundary (its directory is mike-writable) but restarting
Velocity to pick up the change needs a human's explicit go-ahead, since
it's a live restart of the shared proxy.
"""

from __future__ import annotations

from minecraftmgr.constants import REALM_DOMAIN
from minecraftmgr.models.server_entry import ServerEntry


def render_server_add_command(server: ServerEntry) -> str:
    """Render the exact `minecraftmgr server add` invocation for the dev box."""

    return (
        f"minecraftmgr server add {server.server_id} "
        f'--name "{server.name}" --port {server.port} '
        f"--mc-version {server.minecraft_version} --type {server.server_type} "
        f"--data-dir {server.data_dir}"
    )


def render_velocity_snippet(server: ServerEntry, backend_port: int) -> str:
    """Render the [servers]/[forced-hosts] lines to add to velocity.toml."""

    return (
        "[servers]\n"
        f'{server.server_id} = "127.0.0.1:{backend_port}"\n'
        "\n"
        "[forced-hosts]\n"
        f'"{server.server_id}.{REALM_DOMAIN}" = [\n'
        f'    "{server.server_id}"\n'
        "]\n"
    )


def render_cloudflare_instructions(server: ServerEntry) -> str:
    """Render the manual Cloudflare dashboard steps for this realm's CNAME."""

    return (
        "Cloudflare dashboard -> DNS -> Records -> Add record:\n"
        "  Type: CNAME\n"
        f"  Name: {server.server_id}\n"
        f"  Target: mc.{REALM_DOMAIN}\n"
        "  Proxy status: DNS only (grey cloud)\n"
    )


def render_handoff(server: ServerEntry, backend_port: int) -> str:
    """Render the full three-part handoff block: servers.json, velocity.toml, Cloudflare."""

    return (
        "=== Run this from the DEV BOX, not oscar ===\n"
        "(oscar's checkout can't `git push` -- running this here instead\n"
        " silently creates untracked drift in servers.json that has to be\n"
        " found and manually reconciled later)\n"
        f"{render_server_add_command(server)}\n"
        "\n"
        "=== Add to /opt/mc/_proxy/velocity.toml (mike can edit; minecraft must restart Velocity) ===\n"
        f"{render_velocity_snippet(server, backend_port)}"
        "\n"
        "=== Add in Cloudflare ===\n"
        f"{render_cloudflare_instructions(server)}"
    )
