"""Web commands: build the realm-picker static site."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from minecraftmgr.config import load_settings
from minecraftmgr.services.registry_service import list_servers
from minecraftmgr.services.site_service import build_site

app = typer.Typer(help="Build the realm-picker static site (Cloudflare Pages).")
console = Console()


@app.command("build")
def build(
    output: Path = typer.Option(
        Path("public/index.html"), "--out", help="Where to write the generated page"
    ),
) -> None:
    """Render servers.json into the realm-picker page."""

    settings = load_settings()
    servers = list_servers(settings)

    if not servers:
        console.print("[yellow]No realms registered, generating an empty page[/yellow]")

    path = build_site(servers, output)

    console.print(f"[green]Built[/green] {path} ({len(servers)} realm(s))")
