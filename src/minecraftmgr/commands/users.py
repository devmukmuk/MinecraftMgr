"""User commands: who has played on each realm, and when."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from minecraftmgr.config import load_settings
from minecraftmgr.services.registry_service import list_servers
from minecraftmgr.services.user_report_service import build_user_report

app = typer.Typer(help="Player activity reports from realm server logs.", no_args_is_help=True)
console = Console()


@app.command("report")
def report(
    server_id: Optional[str] = typer.Argument(None, help="Only this realm. Omit for every realm."),
    active_only: bool = typer.Option(False, "--active-only", help="Skip inactive realms."),
) -> None:
    """Show each player's first and latest day on each realm, active realms first."""

    settings = load_settings()
    servers = list_servers(settings, active_only=active_only)

    if server_id:
        servers = [entry for entry in servers if entry.server_id == server_id]
        if not servers:
            console.print(f"[red]Server '{server_id}' not found[/red]")
            raise typer.Exit(code=1)

    reports = build_user_report(settings, servers)

    groups = (
        ("Active realms", [realm for realm in reports if realm.status == "active"]),
        ("Inactive realms", [realm for realm in reports if realm.status != "active"]),
    )
    for title, group in groups:
        if not group:
            continue

        console.print()
        console.print(f"[bold]{title}[/bold]")

        for realm in group:
            console.print()
            console.print(f"[bold]{realm.server_id}[/bold] - {realm.name}  ({realm.log_folder})")
            for warning in realm.warnings:
                console.print(f"[yellow]{warning}[/yellow]")
            if not realm.users:
                console.print("No players found.")
                continue

            table = Table(show_header=True)
            table.add_column("Player")
            table.add_column("First seen")
            table.add_column("Latest seen")
            table.add_column("Days", justify="right")
            users = sorted(realm.users.values(), key=lambda item: item.latest_seen, reverse=True)
            for user in users:
                table.add_row(
                    user.player,
                    user.first_seen.isoformat(),
                    user.latest_seen.isoformat(),
                    str(len(user.days_seen)),
                )
            console.print(table)
