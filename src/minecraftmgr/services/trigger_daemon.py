"""HTTP daemon behind the AUTOSTART button on the realm-picker page.

Binds to localhost only. Internet reachability comes from a Cloudflare
Tunnel (cloudflared) routing a public hostname to this local port -- never
from an open port on the router. Must run as the `minecraft` system user;
this is what actually starts realm processes, so it must never run under
the `mike` automation account.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from minecraftmgr.config.settings import Settings
from minecraftmgr.services.registry_service import list_servers
from minecraftmgr.services.trigger_service import (
    TriggerError,
    realm_running,
    start_realm,
    verify_pin,
)


class TriggerHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer carrying the MinecraftMgr settings + PIN path each request needs."""

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        mgr_settings: Settings,
        pin_path: Path,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.mgr_settings = mgr_settings
        self.pin_path = pin_path


class TriggerHandler(BaseHTTPRequestHandler):
    server: TriggerHTTPServer  # type: ignore[assignment]

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-Autostart-Pin")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/status":
            servers = list_servers(self.server.mgr_settings)
            statuses = {
                server.server_id: "running" if realm_running(server.data_dir) else "stopped"
                for server in servers
            }
            self._json(200, statuses)
            return

        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self.path.startswith("/start/"):
            self._json(404, {"error": "not found"})
            return

        realm_id = self.path[len("/start/") :]
        pin = self.headers.get("X-Autostart-Pin", "")

        if not verify_pin(self.server.pin_path, pin):
            self._json(403, {"error": "invalid pin"})
            return

        servers = {server.server_id: server for server in list_servers(self.server.mgr_settings)}
        server = servers.get(realm_id)

        if server is None:
            self._json(404, {"error": f"unknown realm '{realm_id}'"})
            return

        try:
            start_realm(server, self.server.mgr_settings.data_root)
        except TriggerError as exc:
            self._json(409, {"error": str(exc)})
            return

        self._json(200, {"status": "starting"})

    def log_message(self, format: str, *args: object) -> None:
        return


def serve(
    mgr_settings: Settings,
    pin_path: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
) -> None:
    """Run the trigger daemon until interrupted."""

    server = TriggerHTTPServer((host, port), TriggerHandler, mgr_settings, pin_path)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
