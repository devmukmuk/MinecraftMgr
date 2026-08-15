"""Realm registry commands: add / list / remove / update."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from minecraftmgr.config import load_settings
from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.registry_service import (
    RegistryError,
    add_server,
    list_servers,
    remove_server,
    update_server,
)

app = typer.Typer(help="Manage the realm registry (servers.json).")
console = Console()


@app.command("add")
def add(
    server_id: str = typer.Argument(..., help="Unique id, e.g. 'gatorland'"),
    name: str = typer.Option(..., "--name", help="Display name"),
    port: int = typer.Option(..., "--port", help="Backend port on oscar"),
    minecraft_version: str = typer.Option(..., "--mc-version", help="Minecraft version"),
    server_type: str = typer.Option("paper", "--type", help="Server jar type (paper, vanilla, fabric, forge)"),
    jar_source: str = typer.Option("", "--jar-source", help="Where the server jar comes from"),
    data_dir: Optional[str] = typer.Option(None, "--data-dir", help="Data directory name (defaults to server_id)"),
    notes: str = typer.Option("", "--notes", help="Free-text notes"),
) -> None:
    """Register a new realm."""

    settings = load_settings()

    entry = ServerEntry(
        server_id=server_id,
        name=name,
        status="active",
        port=port,
        minecraft_version=minecraft_version,
        server_type=server_type,
        jar_source=jar_source,
        data_dir=data_dir or server_id,
        created=datetime.now(timezone.utc).isoformat(),
        notes=notes,
    )

    try:
        add_server(settings, entry)
    except RegistryError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Added[/green] {server_id}")


@app.command("list")
def list_cmd(
    active_only: bool = typer.Option(False, "--active-only", help="Only show active realms"),
) -> None:
    """List realms in the registry."""

    settings = load_settings()
    servers = list_servers(settings, active_only=active_only)

    table = Table()
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Port")
    table.add_column("Version")
    table.add_column("Type")

    for server in servers:
        table.add_row(
            server.server_id,
            server.name,
            server.status,
            str(server.port),
            server.minecraft_version,
            server.server_type,
        )

    console.print(table)


@app.command("remove")
def remove(
    server_id: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation"),
) -> None:
    """Remove a realm from the registry."""

    if not yes:
        typer.confirm(f"Remove '{server_id}' from the registry?", abort=True)

    settings = load_settings()

    try:
        remove_server(settings, server_id)
    except RegistryError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Removed[/green] {server_id}")


@app.command("update")
def update(
    server_id: str = typer.Argument(...),
    name: Optional[str] = typer.Option(None, "--name"),
    status: Optional[str] = typer.Option(None, "--status"),
    port: Optional[int] = typer.Option(None, "--port"),
    minecraft_version: Optional[str] = typer.Option(None, "--mc-version"),
    server_type: Optional[str] = typer.Option(None, "--type"),
    jar_source: Optional[str] = typer.Option(None, "--jar-source"),
    notes: Optional[str] = typer.Option(None, "--notes"),
) -> None:
    """Update fields on an existing realm."""

    changes = {
        key: value
        for key, value in {
            "name": name,
            "status": status,
            "port": port,
            "minecraft_version": minecraft_version,
            "server_type": server_type,
            "jar_source": jar_source,
            "notes": notes,
        }.items()
        if value is not None
    }

    if not changes:
        console.print("[yellow]No fields given, nothing to update[/yellow]")
        raise typer.Exit(code=1)

    settings = load_settings()

    try:
        updated = update_server(settings, server_id, **changes)
    except RegistryError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Updated[/green] {updated.server_id}")
