"""Gravestone commands: find graves (Gravestones mod) that were never picked up."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from minecraftmgr.config import load_settings
from minecraftmgr.services.backup_service import resolve_server_data_dir
from minecraftmgr.services.gravestone_service import scan_gravestones
from minecraftmgr.services.registry_service import list_servers

app = typer.Typer(help="Gravestone reports from realm server logs.", no_args_is_help=True)
console = Console()


@app.command("scan")
def scan(
    server_id: Optional[str] = typer.Argument(None, help="Realm id whose logs/ folder to scan."),
    logs: Optional[Path] = typer.Option(
        None, "--logs", file_okay=False, help="Scan this logs folder instead of a realm's."
    ),
    player: Optional[str] = typer.Option(None, "--player", "-p", help="Only this player (any case)."),
    show_found: bool = typer.Option(False, "--show-found", help="Also list graves that were found."),
) -> None:
    """List gravestones placed but never found, for a realm or a logs folder."""

    if bool(server_id) == bool(logs):
        console.print("[red]Pass exactly one of a server id or --logs[/red]")
        raise typer.Exit(code=1)

    if logs is None:
        settings = load_settings()
        matches = [entry for entry in list_servers(settings) if entry.server_id == server_id]
        if not matches:
            console.print(f"[red]Server '{server_id}' not found[/red]")
            raise typer.Exit(code=1)
        logs = resolve_server_data_dir(settings, matches[0]) / "logs"

    result = scan_gravestones(logs, player=player)

    console.print(f"Gravestones for [bold]{player or 'all players'}[/bold] in {logs}")
    console.print(
        f"Placed: {len(result.placed)}   Found: {len(result.found)}   "
        f"Not found: {len(result.missing)}"
    )
    for warning in result.warnings:
        console.print(f"[yellow]{warning}[/yellow]")

    console.print()
    console.print("[bold red]NOT FOUND[/bold red]")
    for grave in result.missing:
        x, y, z = grave.coord
        console.print(f"{grave.player}  {grave.file} {grave.time}  {grave.dimension}  ({x}, {y}, {z})")

    if show_found:
        console.print()
        console.print("[bold green]FOUND[/bold green]")
        for grave in result.found:
            x, y, z = grave.coord
            found = grave.found_entries[0]
            console.print(
                f"{grave.player}  {grave.file} {grave.time}  {grave.dimension}  ({x}, {y}, {z})  "
                f"found {found.file} {found.time}"
            )
