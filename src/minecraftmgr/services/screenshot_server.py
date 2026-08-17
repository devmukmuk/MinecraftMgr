"""Screenshot HTTP server: serve the organized screenshot tree and gallery page.

Plain stdlib static file serving, no auth -- the gallery is meant to be
reachable from a Cloudflare Tunnel bound to 127.0.0.1, the same pattern
already used by the trigger daemon and Velocity itself on oscar.
"""

from __future__ import annotations

import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def build_server(directory: Path, host: str = "127.0.0.1", port: int = 8899) -> ThreadingHTTPServer:
    """Build (but don't start) a threaded HTTP server rooted at directory."""

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(directory))
    return ThreadingHTTPServer((host, port), handler)


def run_server(directory: Path, host: str = "127.0.0.1", port: int = 8899) -> None:
    """Build and run the screenshot HTTP server until interrupted."""

    server = build_server(directory, host, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
