"""Tests for the screenshot HTTP server."""

from __future__ import annotations

import threading
import urllib.error
import urllib.request
from pathlib import Path

from minecraftmgr.services.screenshot_server import build_server


def test_serves_files_from_directory(tmp_path: Path) -> None:
    """The server returns a file's contents from the served directory."""

    (tmp_path / "report").mkdir()
    (tmp_path / "report" / "index.html").write_text("<h1>Gallery</h1>", encoding="utf-8")

    server = build_server(tmp_path, host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        url = f"http://127.0.0.1:{port}/report/index.html"
        with urllib.request.urlopen(url, timeout=5) as response:
            body = response.read().decode("utf-8")
        assert "<h1>Gallery</h1>" in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_html_responses_are_marked_no_cache(tmp_path: Path) -> None:
    """HTML responses carry a no-cache header so a rebuilt gallery isn't served stale."""

    (tmp_path / "report").mkdir()
    (tmp_path / "report" / "index.html").write_text("<h1>Gallery</h1>", encoding="utf-8")

    server = build_server(tmp_path, host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        url = f"http://127.0.0.1:{port}/report/index.html"
        with urllib.request.urlopen(url, timeout=5) as response:
            cache_control = response.headers.get("Cache-Control")
        assert cache_control == "no-cache, no-store, must-revalidate"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_returns_404_for_missing_file(tmp_path: Path) -> None:
    """A missing path returns 404 instead of raising."""

    server = build_server(tmp_path, host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        raised_404 = False
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/does-not-exist.png", timeout=5)
        except urllib.error.HTTPError as exc:
            raised_404 = exc.code == 404
        assert raised_404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
