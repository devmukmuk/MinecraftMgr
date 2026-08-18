"""Realm commands: inspect, provision, activate, start, stop, status, validate.

Meant to run on oscar as the `minecraft` user -- never the `mike`
automation key, since these start/stop realm processes. `status` and
`validate` don't mutate anything by default (`validate` does with --fix),
but `screen` sessions are per-user, so `status` still has to run as
`minecraft` to see the realms' actual sessions -- checking as any other user
looks like nothing is running, even when it is. `provision`/`activate` never
touch servers.json or velocity.toml themselves; they print the exact
snippets needed to wire the realm in from the dev box / Cloudflare
dashboard.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from minecraftmgr.config import load_settings
from minecraftmgr.config.settings import Settings
from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.capacity_service import CapacityError, start_realm_within_capacity
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
from minecraftmgr.services.realm_validate_service import fix_start_sh, validate_start_sh
from minecraftmgr.services.registry_service import list_servers
from minecraftmgr.services.trigger_service import TriggerError, realm_running, stop_realm

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


def _resolve_targets(settings: Settings, server_id: Optional[str], all_servers: bool) -> list[ServerEntry]:
    if all_servers:
        return list_servers(settings, active_only=True)

    targets = [server for server in list_servers(settings) if server.server_id == server_id]

    if not targets:
        console.print(f"[red]Server '{server_id}' not found[/red]")
        raise typer.Exit(code=1)

    return targets


@app.command("start")
def start_cmd(
    server_id: Optional[str] = typer.Argument(
        None, help="Realm id to start. Omit with --all to start every active realm."
    ),
    all_servers: bool = typer.Option(False, "--all", help="Start every active realm in the registry"),
) -> None:
    """Start a realm's screen session, or every active realm with --all.

    Wraps trigger_service.start_realm() -- the same logic the AUTOSTART
    button already uses for a single realm. Run as the `minecraft` user.
    Capacity-aware: if settings.max_running_servers is already reached, this
    evicts one idle realm (nothing connected to its port) to make room --
    see services/capacity_service.py. `--all` never evicts a realm that's
    also a target in the same batch, to avoid flapping; if nothing outside
    the batch is idle, remaining targets are skipped with a warning instead.
    """

    if bool(server_id) == all_servers:
        console.print("[red]Pass exactly one of a server id or --all[/red]")
        raise typer.Exit(code=1)

    settings = load_settings()
    targets = _resolve_targets(settings, server_id, all_servers)
    every_server = list_servers(settings)
    exclude_from_eviction = {server.server_id for server in targets} if all_servers else set()

    failures: list[str] = []

    for server in targets:
        try:
            evicted = start_realm_within_capacity(
                server,
                every_server,
                settings.data_root,
                max_running=settings.max_running_servers,
                exclude_from_eviction=exclude_from_eviction,
            )
            if evicted is not None:
                console.print(
                    f"[yellow]Stopped idle[/yellow] {evicted.server_id} to make room for "
                    f"[green]{server.server_id}[/green]"
                )
            console.print(f"[green]Started[/green] {server.server_id}")
        except TriggerError as exc:
            console.print(f"[yellow]Skipped[/yellow] {server.server_id}: {exc}")
            failures.append(server.server_id)
        except CapacityError as exc:
            console.print(f"[yellow]Skipped[/yellow] {server.server_id}: {exc}")
            failures.append(server.server_id)

    if failures and not all_servers:
        raise typer.Exit(code=1)


@app.command("stop")
def stop_cmd(
    server_id: Optional[str] = typer.Argument(
        None, help="Realm id to stop. Omit with --all to stop every active realm."
    ),
    all_servers: bool = typer.Option(False, "--all", help="Stop every active realm in the registry"),
) -> None:
    """Stop a realm's screen session (graceful, falling back to a kill), or every active realm with --all.

    Wraps trigger_service.stop_realm() -- already used internally by
    provision/activate's first-boot cycle. Run as the `minecraft` user.
    """

    if bool(server_id) == all_servers:
        console.print("[red]Pass exactly one of a server id or --all[/red]")
        raise typer.Exit(code=1)

    settings = load_settings()
    targets = _resolve_targets(settings, server_id, all_servers)

    for server in targets:
        stop_realm(server, settings.data_root)
        console.print(f"[green]Stopped[/green] {server.server_id}")


@app.command("status")
def status_cmd(
    server_id: Optional[str] = typer.Argument(
        None, help="Realm id to check. Omit to check every registered realm."
    ),
) -> None:
    """Report which registered realms currently have a running screen session.

    Reads live `screen` state, same as trigger_daemon's GET /status -- not
    servers.json's `status` field, which only says whether a realm is meant
    to be active, not whether it's actually running right now.
    """

    settings = load_settings()

    if server_id:
        targets = [server for server in list_servers(settings) if server.server_id == server_id]
        if not targets:
            console.print(f"[red]Server '{server_id}' not found[/red]")
            raise typer.Exit(code=1)
    else:
        targets = list_servers(settings)

    table = Table()
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Registry status")
    table.add_column("Running")

    for server in targets:
        running = realm_running(server.data_dir)
        table.add_row(
            server.server_id,
            server.name,
            server.status,
            "[green]yes[/green]" if running else "[dim]no[/dim]",
        )

    console.print(table)


@app.command("validate")
def validate_cmd(
    server_id: Optional[str] = typer.Argument(
        None, help="Realm id to validate. Omit with --all to validate every registered realm."
    ),
    all_servers: bool = typer.Option(False, "--all", help="Validate every registered realm"),
    fix: bool = typer.Option(
        False, "--fix", help="Regenerate start.sh from the canonical template for any realm with issues"
    ),
) -> None:
    """Check each realm's start.sh against tools/templates/start.sh.template; --fix to regenerate it.

    Only checks the IPv4 flag and the port matching servers.json -- MEM_MIN/
    MEM_MAX aren't modeled in the registry yet, so --fix preserves whatever
    the file already has for those rather than guessing a new value.
    """

    if bool(server_id) == all_servers:
        console.print("[red]Pass exactly one of a server id or --all[/red]")
        raise typer.Exit(code=1)

    settings = load_settings()
    targets = _resolve_targets(settings, server_id, all_servers)

    any_issues = False

    for server in targets:
        realm_dir = settings.data_root / server.data_dir
        validation = validate_start_sh(realm_dir, server)

        if validation.ok:
            console.print(f"[green]OK[/green] {server.server_id}")
            continue

        any_issues = True
        console.print(f"[yellow]{server.server_id}[/yellow]")
        for issue in validation.issues:
            console.print(f"  - {issue}")

        if not fix:
            continue

        if not validation.exists:
            console.print("  [red]Cannot fix: start.sh doesn't exist (needs provision/activate)[/red]")
            continue

        fix_start_sh(realm_dir, server, validation)
        mem_min = validation.current_mem_min or "2G (default)"
        mem_max = validation.current_mem_max or "4G (default)"
        console.print(f"  [green]Fixed[/green] (mem_min={mem_min}, mem_max={mem_max} preserved)")

    if any_issues and not fix and not all_servers:
        raise typer.Exit(code=1)
