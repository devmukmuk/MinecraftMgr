"""MinecraftMgr command-line interface."""

from __future__ import annotations

import typer
from rich.console import Console

from minecraftmgr.commands.backup import app as backup_app
from minecraftmgr.commands.server import app as server_app
from minecraftmgr.commands.web import app as web_app
from minecraftmgr.config import load_settings
from minecraftmgr.services.registry_service import list_servers

app = typer.Typer(
    help="MinecraftMgr command-line tools.",
    invoke_without_command=True,
)

app.add_typer(server_app, name="server")
app.add_typer(backup_app, name="backup")
app.add_typer(web_app, name="web")

console = Console()


@app.callback()
def main(ctx: typer.Context) -> None:
    """Run MinecraftMgr."""

    if ctx.invoked_subcommand is None:
        about()


@app.command()
def about() -> None:
    """Print MinecraftMgr environment details."""

    settings = load_settings()

    console.print("[bold]MinecraftMgr[/bold]")
    console.print()

    console.print("[bold]Config[/bold]")
    console.print(f"Path: {settings.metadata.config_path}")
    console.print(f"Source: {settings.metadata.config_source}")
    console.print(f"Defaults Created: {settings.metadata.defaults_created}")
    console.print()

    console.print("[bold]Resolved Paths[/bold]")
    console.print(f"Data Root: {settings.data_root}")
    console.print(f"Backups Root: {settings.backups_root}")
    console.print(f"Servers Registry: {settings.servers_json_path}")
    console.print()

    servers = list_servers(settings)

    console.print("[bold]Realms[/bold]")

    if servers:
        for server in servers:
            console.print(f"- {server.server_id} ({server.status}) - {server.name}")
    else:
        console.print("- None registered yet")
