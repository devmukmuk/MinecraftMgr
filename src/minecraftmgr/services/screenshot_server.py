"""Screenshot HTTP server: serve the organized screenshot tree and gallery page.

Plain stdlib static file serving, no auth -- the gallery is meant to be
reachable from a Cloudflare Tunnel bound to 127.0.0.1, the same pattern
already used by the trigger daemon and Velocity itself on oscar.
"""

from __future__ import annotations

import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _NoCacheHTMLRequestHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler that stops browsers from caching stale HTML.

    The gallery is rebuilt in place (organize/build-gallery overwrite
    report/index.html) with no filename change, so a cached HTML response
    would keep showing an old manifest indefinitely. Images under
    <realm>/<version>/ never change once written, so only .html responses
    get the no-cache treatment.
    """

    def end_headers(self) -> None:
        if self.path.endswith(".html") or self.path.endswith("/"):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()


def build_server(directory: Path, host: str = "127.0.0.1", port: int = 8899) -> ThreadingHTTPServer:
    """Build (but don't start) a threaded HTTP server rooted at directory."""

    handler = functools.partial(_NoCacheHTMLRequestHandler, directory=str(directory))
    return ThreadingHTTPServer((host, port), handler)


def run_server(directory: Path, host: str = "127.0.0.1", port: int = 8899) -> None:
    """Build and run the screenshot HTTP server until interrupted."""

    server = build_server(directory, host, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
