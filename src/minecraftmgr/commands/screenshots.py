"""Screenshot commands: organize captures by realm/version and build the gallery page."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from minecraftmgr.config import load_settings
from minecraftmgr.services.gallery_service import build_gallery
from minecraftmgr.services.registry_service import list_servers
from minecraftmgr.services.screenshot_matcher_service import (
    load_manifest,
    organize_screenshots,
    write_manifest,
)
from minecraftmgr.services.screenshot_server import run_server

app = typer.Typer(help="Organize screenshots by realm/version and build the gallery page.")
console = Console()

_SCREENSHOTS_SUBDIR = "_screenshots"
_MANIFEST_NAME = "manifest.json"


@app.command("organize")
def organize(
    username: str = typer.Option(
        ..., "--username", help="Minecraft username to match against realm join/leave logs"
    ),
    inbox: Optional[Path] = typer.Option(
        None, "--inbox", help="Folder of unsorted screenshots (default: <output>/_inbox)"
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", help="Organized-tree root (default: <data_root>/_screenshots)"
    ),
    slack_seconds: int = typer.Option(
        5, "--slack-seconds", help="Clock-skew tolerance applied at session boundaries"
    ),
) -> None:
    """Match inbox screenshots to a realm session and move them into an organized tree."""

    settings = load_settings()
    output_root = output or settings.data_root / _SCREENSHOTS_SUBDIR
    inbox_dir = inbox or output_root / "_inbox"

    servers = list_servers(settings)
    realm_logs = {
        server.server_id: (settings.data_root / server.data_dir / "logs", server.minecraft_version)
        for server in servers
    }

    matches = organize_screenshots(
        inbox_dir,
        output_root,
        realm_logs,
        username,
        slack=timedelta(seconds=slack_seconds),
    )

    manifest_path = write_manifest(matches, output_root / _MANIFEST_NAME)

    matched = sum(1 for match in matches if match.matched)
    console.print(
        f"[green]Organized[/green] {len(matches)} screenshot(s), {matched} matched to a realm"
    )
    console.print(f"Manifest: {manifest_path}")


@app.command("build-gallery")
def build_gallery_command(
    manifest: Optional[Path] = typer.Option(
        None, "--manifest", help="Manifest to read (default: <data_root>/_screenshots/manifest.json)"
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Where to write the gallery page (default: <manifest folder>/report/index.html)"
    ),
) -> None:
    """Render the filterable screenshot gallery from an organize manifest."""

    settings = load_settings()
    manifest_path = manifest or settings.data_root / _SCREENSHOTS_SUBDIR / _MANIFEST_NAME
    matches = load_manifest(manifest_path)

    output_path = out or manifest_path.parent / "report" / "index.html"
    path = build_gallery(matches, output_path)

    console.print(f"[green]Built[/green] {path} ({len(matches)} screenshot(s))")


@app.command("serve")
def serve(
    directory: Optional[Path] = typer.Option(
        None, "--directory", help="Root to serve (default: <data_root>/_screenshots)"
    ),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address"),
    port: int = typer.Option(8899, "--port", help="Bind port"),
) -> None:
    """Serve the organized screenshot tree and gallery page over plain HTTP.

    Meant to sit behind a Cloudflare Tunnel bound to 127.0.0.1, the same
    pattern already used by the trigger daemon and Velocity on oscar.
    """

    settings = load_settings()
    root = directory or settings.data_root / _SCREENSHOTS_SUBDIR

    if not root.is_dir():
        console.print(f"[red]Directory not found:[/red] {root}")
        raise typer.Exit(code=1)

    console.print(f"[green]Serving[/green] {root} at http://{host}:{port}/report/")
    run_server(root, host, port)
