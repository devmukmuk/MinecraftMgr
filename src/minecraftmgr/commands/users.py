"""User commands: who has played on each realm, and when."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from minecraftmgr.config import load_settings
from minecraftmgr.services.registry_service import list_servers
from minecraftmgr.services.user_report_service import build_user_report, realm_rows

app = typer.Typer(help="Player activity reports from realm server logs.", no_args_is_help=True)
console = Console()


@app.command("report")
def report(
    server_id: Optional[str] = typer.Argument(None, help="Only this realm. Omit for every realm."),
    active_only: bool = typer.Option(False, "--active-only", help="Skip inactive and archived realms."),
) -> None:
    """Show each realm's players: active, inactive, then archived realms.

    Ops are marked OP; whitelisted players who never joined are listed as "not yet".

    Archived realms are included (their logs are under <data_root>/_archive/) so
    retiring a realm doesn't lose who played on it; --active-only skips both.
    """

    settings = load_settings()
    servers = list_servers(settings, active_only=active_only, include_archived=True)

    if server_id:
        servers = [entry for entry in servers if entry.server_id == server_id]
        if not servers:
            console.print(f"[red]Server '{server_id}' not found[/red]")
            raise typer.Exit(code=1)

    reports = build_user_report(settings, servers)

    groups = (
        ("Active realms", [realm for realm in reports if realm.status == "active"]),
        ("Inactive realms", [realm for realm in reports if realm.status == "inactive"]),
        ("Archived realms", [realm for realm in reports if realm.status == "archived"]),
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
            rows = realm_rows(realm)
            if not rows:
                console.print("No players found.")
                continue

            table = Table(show_header=True)
            table.add_column("Player")
            table.add_column("First seen")
            table.add_column("Latest seen")
            table.add_column("Days", justify="right")
            for row in rows:
                name = escape(row["player"])
                if row["op"]:
                    name += " [black on yellow] OP [/]"
                table.add_row(
                    name,
                    row["first_seen"] or "[dim]not yet[/dim]",
                    row["latest_seen"] or "[dim]not yet[/dim]",
                    str(row["days"]),
                )
            console.print(table)
