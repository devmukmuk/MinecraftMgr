"""Realm provisioning commands: inspect, provision, activate.

Meant to run on oscar as the `minecraft` user -- never the `mike`
automation key, since these start/stop realm processes. They never touch
servers.json or velocity.toml themselves; they print the exact snippets
needed to wire the realm in from the dev box / Cloudflare dashboard.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from minecraftmgr.config import load_settings
from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.jar_cache_service import JarCacheError, ensure_jar_cached
from minecraftmgr.services.provision_service import (
    ReadinessTimeout,
    RealmCrashedBeforeReady,
    first_boot_cycle,
    patch_velocity_trust,
)
from minecraftmgr.services.realm_handoff_service import render_handoff
from minecraftmgr.services.realm_inspect_service import (
    IncompatibleRealmError,
    inspect_realm_dir,
    require_velocity_compatible,
)
from minecraftmgr.services.realm_scaffold_service import ScaffoldError, scaffold_realm_dir

app = typer.Typer(help="Provision or activate a realm's data directory on oscar.")
console = Console()


def _forwarding_secret(data_root: Path) -> str:
    secret_path = data_root / "_proxy" / "forwarding.secret"

    if not secret_path.exists():
        console.print(f"[red]Velocity forwarding secret not found:[/red] {secret_path}")
        raise typer.Exit(code=1)

    return secret_path.read_text(encoding="utf-8").strip()


@app.command("inspect")
def inspect_cmd(data_dir: str = typer.Argument(..., help="Realm folder name under data_root")) -> None:
    """Read-only: report what's actually in a realm's data directory."""

    settings = load_settings()
    inspection = inspect_realm_dir(settings.data_root / data_dir)

    console.print(f"[bold]{inspection.data_dir}[/bold]")
    console.print(f"  Detected type:   {inspection.detected_server_type}")
    console.print(f"  Jar:             {inspection.jar_path or '(none found)'}")
    console.print(f"  Main-Class:      {inspection.jar_main_class or '(unknown)'}")
    console.print(f"  Has mods/:       {inspection.has_mods_dir}")
    console.print(f"  online-mode:     {inspection.online_mode_currently_true}")
    console.print(f"  Current port:    {inspection.current_port or '(unknown)'}")
    console.print(f"  paper-global.yml exists: {inspection.has_paper_global_yml}")

    for note in inspection.notes:
        console.print(f"  [yellow]Note:[/yellow] {note}")

    if inspection.detected_server_type == "paper":
        console.print("[green]Velocity-compatible.[/green]")
    else:
        console.print(
            f"[yellow]Not Velocity-compatible as-is "
            f"(detected '{inspection.detected_server_type}').[/yellow]"
        )


@app.command("provision")
def provision_cmd(
    server_id: str = typer.Argument(..., help="Realm id, e.g. 'gatorland'"),
    name: str = typer.Option(..., "--name", help="Display name"),
    port: int = typer.Option(..., "--port", help="Backend port for Velocity to forward to"),
    minecraft_version: str = typer.Option(..., "--mc-version", help="Minecraft version"),
    mem_min: str = typer.Option("2G", "--mem-min"),
    mem_max: str = typer.Option("4G", "--mem-max"),
    data_dir: Optional[str] = typer.Option(None, "--data-dir", help="Defaults to server_id"),
    force: bool = typer.Option(False, "--force", help="Overwrite a non-empty target directory"),
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the plan, don't touch disk"),
) -> None:
    """Scaffold a brand-new Velocity-ready realm from scratch: jar, folder, first boot, trust config."""

    settings = load_settings()
    resolved_data_dir = data_dir or server_id
    realm_dir = settings.data_root / resolved_data_dir

    entry = ServerEntry(
        server_id=server_id,
        name=name,
        status="active",
        port=port,
        minecraft_version=minecraft_version,
        server_type="paper",
        jar_source="",
        data_dir=resolved_data_dir,
        created=datetime.now(timezone.utc).isoformat(),
        notes="",
    )

    if dry_run:
        console.print(f"[bold]Would provision[/bold] {realm_dir}")
        console.print(f"  jar for {minecraft_version} from _jarcache")
        console.print(f"  mem: {mem_min}/{mem_max}, port: {port}")
        console.print("  first-boot cycle to generate config/paper-global.yml")
        console.print("  patch Velocity trust config")
        return

    if not yes:
        typer.confirm(f"Provision '{server_id}' at {realm_dir}?", abort=True)

    try:
        jar_path = ensure_jar_cached(settings.data_root, minecraft_version)
    except JarCacheError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    try:
        scaffold_realm_dir(
            realm_dir,
            jar_path=jar_path,
            data_dir=resolved_data_dir,
            port=port,
            mem_min=mem_min,
            mem_max=mem_max,
            force=force,
        )
    except ScaffoldError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Scaffolded[/green] {realm_dir}, starting first boot...")

    try:
        paper_global_path = first_boot_cycle(entry, settings.data_root)
    except (ReadinessTimeout, RealmCrashedBeforeReady) as exc:
        console.print(f"[red]{exc}[/red]")
        console.print(
            f"[yellow]The realm's directory is scaffolded but its Velocity trust config isn't "
            f"patched yet. Check it with `screen -r {resolved_data_dir}`, then re-run once it's "
            f"stopped.[/yellow]"
        )
        raise typer.Exit(code=1)

    secret = _forwarding_secret(settings.data_root)
    patch_velocity_trust(paper_global_path, secret)

    console.print("[green]First boot complete, Velocity trust configured.[/green]")
    console.print()
    console.print(render_handoff(entry, backend_port=port))


@app.command("activate")
def activate_cmd(
    data_dir: str = typer.Argument(..., help="Existing realm folder name under data_root"),
    name: str = typer.Option(..., "--name", help="Display name"),
    minecraft_version: str = typer.Option(..., "--mc-version", help="Minecraft version"),
    port: Optional[int] = typer.Option(
        None, "--port", help="Defaults to the port already in server.properties"
    ),
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the plan, don't touch disk"),
) -> None:
    """Make an existing, already-sitting realm Velocity-ready. Refuses anything not positively Paper."""

    settings = load_settings()
    realm_dir = settings.data_root / data_dir

    inspection = inspect_realm_dir(realm_dir)

    try:
        require_velocity_compatible(inspection)
    except IncompatibleRealmError as exc:
        console.print(f"[red]{exc}[/red]")
        for note in inspection.notes:
            console.print(f"  [yellow]Note:[/yellow] {note}")
        raise typer.Exit(code=1)

    resolved_port = port or inspection.current_port
    if resolved_port is None:
        console.print("[red]No port found in server.properties and none given via --port[/red]")
        raise typer.Exit(code=1)

    entry = ServerEntry(
        server_id=data_dir,
        name=name,
        status="active",
        port=resolved_port,
        minecraft_version=minecraft_version,
        server_type="paper",
        jar_source="",
        data_dir=data_dir,
        created=datetime.now(timezone.utc).isoformat(),
        notes="",
    )

    if dry_run:
        console.print(f"[bold]Would activate[/bold] {realm_dir} (detected Paper, port {resolved_port})")
        if not inspection.has_paper_global_yml:
            console.print("  first-boot cycle to generate config/paper-global.yml")
        console.print("  patch Velocity trust config")
        console.print("  flip server.properties to online-mode=false, server-ip=127.0.0.1")
        return

    if not yes:
        typer.confirm(f"Activate '{data_dir}' at {realm_dir}?", abort=True)

    properties_path = realm_dir / "server.properties"
    text = properties_path.read_text(encoding="utf-8")
    text = "\n".join(
        line
        for line in text.splitlines()
        if not line.startswith("online-mode=") and not line.startswith("server-ip=")
    )
    text += "\nonline-mode=false\nserver-ip=127.0.0.1\n"
    properties_path.write_text(text, encoding="utf-8")

    if inspection.has_paper_global_yml:
        paper_global_path = realm_dir / "config" / "paper-global.yml"
    else:
        console.print("[green]server.properties updated[/green], starting first boot...")
        try:
            paper_global_path = first_boot_cycle(entry, settings.data_root)
        except (ReadinessTimeout, RealmCrashedBeforeReady) as exc:
            console.print(f"[red]{exc}[/red]")
            console.print(
                f"[yellow]Check it with `screen -r {data_dir}`, then re-run once it's stopped.[/yellow]"
            )
            raise typer.Exit(code=1)

    secret = _forwarding_secret(settings.data_root)
    patch_velocity_trust(paper_global_path, secret)

    console.print("[green]Velocity trust configured.[/green]")
    console.print()
    console.print(render_handoff(entry, backend_port=resolved_port))
