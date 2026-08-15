"""Backup commands: back up one realm or all realms."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from minecraftmgr.config import load_settings
from minecraftmgr.services.backup_service import backup_servers
from minecraftmgr.services.registry_service import list_servers

app = typer.Typer(help="Back up realm data directories.")
console = Console()


@app.command("run")
def run(
    server_id: Optional[str] = typer.Argument(
        None, help="Realm id to back up. Omit with --all to back up every realm."
    ),
    all_servers: bool = typer.Option(False, "--all", help="Back up every realm in the registry"),
) -> None:
    """Back up a specific realm, or every realm with --all."""

    if bool(server_id) == all_servers:
        console.print("[red]Pass exactly one of a server id or --all[/red]")
        raise typer.Exit(code=1)

    settings = load_settings()
    servers = list_servers(settings)

    if not all_servers:
        servers = [server for server in servers if server.server_id == server_id]

        if not servers:
            console.print(f"[red]Server '{server_id}' not found[/red]")
            raise typer.Exit(code=1)

    results, failures = backup_servers(settings, servers)

    for result in results:
        console.print(
            f"[green]Backed up[/green] {result.server_id} -> "
            f"{result.archive_path.name} ({result.size_bytes:,} bytes)"
        )

    for failed_id, reason in failures:
        console.print(f"[red]Failed[/red] {failed_id}: {reason}")

    if failures:
        raise typer.Exit(code=1)
