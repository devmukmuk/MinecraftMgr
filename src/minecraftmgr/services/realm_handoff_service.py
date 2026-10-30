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

from minecraftmgr.constants import OSCAR_LAN_IP, REALM_DOMAIN
from minecraftmgr.models.server_entry import ServerEntry


def render_server_add_command(server: ServerEntry) -> str:
    """Render the exact `minecraftmgr server add` invocation for the dev box."""

    return (
        f"minecraftmgr server add {server.server_id} "
        f'--name "{server.name}" --port {server.port} '
        f"--mc-version {server.minecraft_version} --type {server.server_type} "
        f"--data-dir {server.data_dir}"
        + (f" --mode {server.mode}" if server.mode != "survival" else "")
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


def render_hosts_line(server: ServerEntry) -> str:
    """Render the hosts-file line that lets PCs inside the house reach this realm."""

    return f"{OSCAR_LAN_IP} {server.server_id}.{REALM_DOMAIN}"


def render_handoff(server: ServerEntry, backend_port: int) -> str:
    """Render the full handoff block: servers.json, velocity.toml, Cloudflare, home PCs' hosts file."""

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
        "\n"
        "=== On each Windows PC at home: hosts file (Notepad as Administrator) ===\n"
        "(the AT&T gateway can't reliably loop home PCs out to the public IP and back;\n"
        " without this line, joining works once, then 'Connection timed out: getsockopt')\n"
        "C:\\Windows\\System32\\drivers\\etc\\hosts:\n"
        f"  {render_hosts_line(server)}\n"
        "then, in an admin PowerShell: ipconfig /flushdns\n"
    )
