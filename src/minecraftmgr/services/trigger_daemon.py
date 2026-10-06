"""HTTP daemon behind the AUTOSTART button on the realm-picker page.

Binds to localhost only. Internet reachability comes from a Cloudflare
Tunnel (cloudflared) routing a public hostname to this local port -- never
from an open port on the router. Must run as the `minecraft` system user;
this is what actually starts realm processes, so it must never run under
the `mike` automation account.
"""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from minecraftmgr.config.settings import Settings
from minecraftmgr.services.capacity_service import CapacityError, start_realm_within_capacity
from minecraftmgr.services.registry_service import list_servers
from minecraftmgr.services.trigger_service import (
    TriggerError,
    proxy_listening,
    realm_running,
    verify_pin,
)
from minecraftmgr.services.user_report_service import players_by_realm


PLAYERS_CACHE_SECONDS = 300


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
        self.players_cache: tuple[float, dict] | None = None


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
            # "_proxy" can't clash with a realm id; the page shows a banner when it's stopped.
            statuses["_proxy"] = "running" if proxy_listening() else "stopped"
            self._json(200, statuses)
            return

        self._json(404, {"error": "not found"})

    def _players(self) -> dict:
        """Return per-realm player activity, re-reading the logs at most every PLAYERS_CACHE_SECONDS."""

        cached = self.server.players_cache
        if cached is not None and time.monotonic() - cached[0] < PLAYERS_CACHE_SECONDS:
            return cached[1]

        settings = self.server.mgr_settings
        data = players_by_realm(settings, list_servers(settings))
        self.server.players_cache = (time.monotonic(), data)
        return data

    def do_POST(self) -> None:
        if self.path == "/players":
            # Player names and play dates are family-only: same PIN as Autostart.
            if not verify_pin(self.server.pin_path, self.headers.get("X-Autostart-Pin", "")):
                self._json(403, {"error": "invalid pin"})
                return
            self._json(200, self._players())
            return

        if not self.path.startswith("/start/"):
            self._json(404, {"error": "not found"})
            return

        realm_id = self.path[len("/start/") :]
        pin = self.headers.get("X-Autostart-Pin", "")

        if not verify_pin(self.server.pin_path, pin):
            self._json(403, {"error": "invalid pin"})
            return

        all_servers = list_servers(self.server.mgr_settings)
        servers = {server.server_id: server for server in all_servers}
        server = servers.get(realm_id)

        if server is None:
            self._json(404, {"error": f"unknown realm '{realm_id}'"})
            return

        try:
            evicted = start_realm_within_capacity(
                server,
                all_servers,
                self.server.mgr_settings.data_root,
                max_running=self.server.mgr_settings.max_running_servers,
            )
        except TriggerError as exc:
            self._json(409, {"error": str(exc)})
            return
        except CapacityError as exc:
            self._json(503, {"error": str(exc)})
            return

        payload = {"status": "starting"}
        if evicted is not None:
            payload["evicted"] = evicted.server_id

        self._json(200, payload)

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
