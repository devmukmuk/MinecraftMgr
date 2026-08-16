"""Trigger commands: run the realm status/start daemon behind the AUTOSTART button."""

from __future__ import annotations

import typer
from rich.console import Console

from minecraftmgr.config import load_settings
from minecraftmgr.services.trigger_daemon import serve

app = typer.Typer(help="Run the realm start/status trigger daemon (Cloudflare Tunnel target).")
console = Console()


@app.command("serve")
def serve_cmd(
    host: str = typer.Option(
        "127.0.0.1", "--host", help="Bind address (the tunnel handles the internet-facing side)"
    ),
    port: int = typer.Option(8787, "--port", help="Bind port"),
) -> None:
    """Start the trigger daemon. Run as the `minecraft` user, never the automation account."""

    settings = load_settings()
    pin_path = settings.data_root / "_trigger" / "pin.secret"

    if not pin_path.exists():
        console.print(f"[red]PIN file not found:[/red] {pin_path}")
        console.print(
            f"Create it first, e.g.: mkdir -p {pin_path.parent} "
            f"&& printf '%s' 'your-pin' > {pin_path}"
        )
        raise typer.Exit(code=1)

    console.print(f"[green]Trigger daemon listening[/green] on {host}:{port}")
    console.print(f"PIN file: {pin_path}")

    serve(settings, pin_path, host=host, port=port)
