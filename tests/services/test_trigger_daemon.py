"""Tests for the trigger HTTP daemon (status + start endpoints)."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterator

import pytest

from minecraftmgr.config.settings import Settings
from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services import trigger_daemon
from minecraftmgr.services.registry_service import add_server
from minecraftmgr.services.trigger_service import TriggerError


def _entry(server_id: str) -> ServerEntry:
    return ServerEntry(
        server_id=server_id,
        name=server_id.title(),
        status="active",
        port=25565,
        minecraft_version="1.21.10",
        server_type="paper",
        jar_source="",
        data_dir=server_id,
        created="2026-08-15T21:00:00+00:00",
        notes="",
    )


@pytest.fixture
def running_daemon(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[str, list[str]]]:
    """Start a real trigger daemon on an ephemeral port, with screen/start faked out."""

    add_server(settings, _entry("gravestone"))
    add_server(settings, _entry("jitterbug"))

    pin_path = tmp_path / "pin.secret"
    pin_path.write_text("1234", encoding="utf-8")

    monkeypatch.setattr(
        trigger_daemon, "realm_running", lambda data_dir, **_: data_dir == "gravestone"
    )

    started: list[str] = []

    def fake_start_realm(server: ServerEntry, data_root: Path, **_: object) -> None:
        if server.server_id in started:
            raise TriggerError("already running")
        started.append(server.server_id)

    monkeypatch.setattr(trigger_daemon, "start_realm", fake_start_realm)

    server = trigger_daemon.TriggerHTTPServer(
        ("127.0.0.1", 0), trigger_daemon.TriggerHandler, settings, pin_path
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    yield base_url, started

    server.shutdown()
    thread.join(timeout=5)


def test_status_reports_running_and_stopped(running_daemon: tuple[str, list[str]]) -> None:
    """GET /status reflects the (faked) live screen session state per realm."""

    base_url, _ = running_daemon

    with urllib.request.urlopen(f"{base_url}/status") as res:
        body = json.loads(res.read())

    assert body == {"gravestone": "running", "jitterbug": "stopped"}


def test_start_with_correct_pin_starts_realm(running_daemon: tuple[str, list[str]]) -> None:
    """POST /start/<id> with the right PIN actually starts the realm."""

    base_url, started = running_daemon

    req = urllib.request.Request(
        f"{base_url}/start/jitterbug", method="POST", headers={"X-Autostart-Pin": "1234"}
    )
    with urllib.request.urlopen(req) as res:
        assert res.status == 200

    assert started == ["jitterbug"]


def test_start_with_wrong_pin_rejected(running_daemon: tuple[str, list[str]]) -> None:
    """A wrong PIN is rejected with 403 and never starts anything."""

    base_url, started = running_daemon

    req = urllib.request.Request(
        f"{base_url}/start/jitterbug", method="POST", headers={"X-Autostart-Pin": "0000"}
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)

    assert exc_info.value.code == 403
    assert started == []


def test_start_unknown_realm_returns_404(running_daemon: tuple[str, list[str]]) -> None:
    """Starting a realm_id that isn't in the registry is a 404, not a crash."""

    base_url, _ = running_daemon

    req = urllib.request.Request(
        f"{base_url}/start/nope", method="POST", headers={"X-Autostart-Pin": "1234"}
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)

    assert exc_info.value.code == 404


def test_cors_header_present_on_status(running_daemon: tuple[str, list[str]]) -> None:
    """The picker page (a different origin) must be able to read the response."""

    base_url, _ = running_daemon

    with urllib.request.urlopen(f"{base_url}/status") as res:
        assert res.headers["Access-Control-Allow-Origin"] == "*"
