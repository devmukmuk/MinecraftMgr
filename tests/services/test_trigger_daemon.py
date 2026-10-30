"""Tests for the trigger HTTP daemon (status, start, players and hardcore endpoints)."""

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
from minecraftmgr.services.capacity_service import CapacityError
from minecraftmgr.services.hardcore_service import HardcoreError
from minecraftmgr.services.registry_service import add_server
from minecraftmgr.services.trigger_service import TriggerError


def _entry(server_id: str, status: str = "active") -> ServerEntry:
    return ServerEntry(
        server_id=server_id,
        name=server_id.title(),
        status=status,
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
    add_server(settings, _entry("cave", status="archived"))

    pin_path = tmp_path / "pin.secret"
    pin_path.write_text("1234", encoding="utf-8")

    monkeypatch.setattr(
        trigger_daemon, "realm_running", lambda data_dir, **_: data_dir == "gravestone"
    )
    monkeypatch.setattr(trigger_daemon, "proxy_listening", lambda: True)

    started: list[str] = []

    def fake_start_realm_within_capacity(
        server: ServerEntry, all_servers: list[ServerEntry], data_root: Path, **_: object
    ) -> ServerEntry | None:
        if server.server_id in started:
            raise TriggerError("already running")
        started.append(server.server_id)
        return None

    monkeypatch.setattr(
        trigger_daemon, "start_realm_within_capacity", fake_start_realm_within_capacity
    )

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

    assert body == {"gravestone": "running", "jitterbug": "stopped", "_proxy": "running"}


def test_status_reports_proxy_stopped(
    running_daemon: tuple[str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /status says _proxy is stopped when Velocity isn't accepting connections."""

    base_url, _ = running_daemon
    monkeypatch.setattr(trigger_daemon, "proxy_listening", lambda: False)

    with urllib.request.urlopen(f"{base_url}/status") as res:
        assert json.loads(res.read())["_proxy"] == "stopped"


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


def test_archived_realm_is_hidden_and_cannot_be_started(
    running_daemon: tuple[str, list[str]],
) -> None:
    """An archived realm is left out of /status and /start/<id> treats it as unknown."""

    base_url, started = running_daemon

    with urllib.request.urlopen(f"{base_url}/status") as res:
        assert "cave" not in json.loads(res.read())

    req = urllib.request.Request(
        f"{base_url}/start/cave", method="POST", headers={"X-Autostart-Pin": "1234"}
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)

    assert exc_info.value.code == 404
    assert started == []


def test_start_at_capacity_returns_503(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CapacityError (at cap, nothing idle) maps to 503, not a crash or a silent no-op."""

    add_server(settings, _entry("gravestone"))
    pin_path = tmp_path / "pin.secret"
    pin_path.write_text("1234", encoding="utf-8")

    def raise_capacity_error(*args: object, **kwargs: object) -> None:
        raise CapacityError("3 realms already running and none are idle -- try again shortly")

    monkeypatch.setattr(trigger_daemon, "start_realm_within_capacity", raise_capacity_error)

    server = trigger_daemon.TriggerHTTPServer(
        ("127.0.0.1", 0), trigger_daemon.TriggerHandler, settings, pin_path
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        req = urllib.request.Request(
            f"{base_url}/start/gravestone", method="POST", headers={"X-Autostart-Pin": "1234"}
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)

        assert exc_info.value.code == 503
        body = json.loads(exc_info.value.read())
        assert "try again shortly" in body["error"]
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_start_reports_evicted_realm_in_response(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When starting evicts an idle realm to make room, the response says which one."""

    add_server(settings, _entry("gravestone"))
    add_server(settings, _entry("jitterbug"))
    pin_path = tmp_path / "pin.secret"
    pin_path.write_text("1234", encoding="utf-8")

    def fake_start_with_eviction(
        server: ServerEntry, all_servers: list[ServerEntry], data_root: Path, **_: object
    ) -> ServerEntry:
        return _entry("jitterbug")

    monkeypatch.setattr(trigger_daemon, "start_realm_within_capacity", fake_start_with_eviction)

    server = trigger_daemon.TriggerHTTPServer(
        ("127.0.0.1", 0), trigger_daemon.TriggerHandler, settings, pin_path
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        req = urllib.request.Request(
            f"{base_url}/start/gravestone", method="POST", headers={"X-Autostart-Pin": "1234"}
        )
        with urllib.request.urlopen(req) as res:
            body = json.loads(res.read())

        assert body == {"status": "starting", "evicted": "jitterbug"}
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_cors_header_present_on_status(running_daemon: tuple[str, list[str]]) -> None:
    """The picker page (a different origin) must be able to read the response."""

    base_url, _ = running_daemon

    with urllib.request.urlopen(f"{base_url}/status") as res:
        assert res.headers["Access-Control-Allow-Origin"] == "*"


def _post_players(base_url: str, pin: str) -> urllib.request.Request:
    return urllib.request.Request(
        f"{base_url}/players", method="POST", headers={"X-Autostart-Pin": pin}
    )


def test_players_requires_the_family_pin(running_daemon: tuple[str, list[str]]) -> None:
    """POST /players with a wrong or missing PIN is 403 and reveals nothing."""

    base_url, _ = running_daemon

    for pin in ("0000", ""):
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(_post_players(base_url, pin))
        assert exc_info.value.code == 403
        assert b"FourEight" not in exc_info.value.read()


def test_players_returns_activity_per_realm_and_caches(
    running_daemon: tuple[str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the PIN, /players returns each realm's players; logs are re-read at most every 5 min."""

    base_url, _ = running_daemon
    calls: list[list[str]] = []

    def fake_players(_settings, servers):
        calls.append([server.server_id for server in servers])
        return {"gravestone": [{"player": "FourEight1516", "first_seen": "2025-09-30",
                                "latest_seen": "2026-10-05", "days": 209}]}

    monkeypatch.setattr(trigger_daemon, "players_by_realm", fake_players)

    for _ in range(2):
        with urllib.request.urlopen(_post_players(base_url, "1234")) as res:
            body = json.loads(res.read())
            assert res.headers["Access-Control-Allow-Origin"] == "*"

    assert body["gravestone"][0]["days"] == 209
    assert calls == [["gravestone", "jitterbug"]]  # archived "cave" left out, second call cached


def _post(base_url: str, path: str, pin: str, body: dict | None = None) -> urllib.request.Request:
    headers = {"X-Autostart-Pin": pin}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    return urllib.request.Request(f"{base_url}{path}", data=data, method="POST", headers=headers)


@pytest.mark.parametrize("path", ["/hardcore", "/reset/gravestone"])
def test_hardcore_endpoints_require_the_family_pin(
    running_daemon: tuple[str, list[str]], monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """Hardcore summaries and Archive & Reset are 403 without the PIN, and reset nothing."""

    base_url, _ = running_daemon
    resets: list[str] = []
    monkeypatch.setattr(
        trigger_daemon, "archive_and_reset", lambda _s, server, seed: resets.append(server.server_id)
    )

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(_post(base_url, path, "0000"))

    assert exc_info.value.code == 403
    assert resets == []


def test_hardcore_returns_the_report(
    running_daemon: tuple[str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    base_url, _ = running_daemon
    monkeypatch.setattr(
        trigger_daemon,
        "hardcore_report",
        lambda _s, servers: {"hardcore": {"current": {"players": []}, "runs": []}},
    )

    with urllib.request.urlopen(_post(base_url, "/hardcore", "1234")) as res:
        assert json.loads(res.read()) == {"hardcore": {"current": {"players": []}, "runs": []}}


def test_reset_passes_the_seed_and_returns_the_run(
    running_daemon: tuple[str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    from minecraftmgr.models.hardcore_run import HardcoreRun

    base_url, _ = running_daemon
    calls: list[tuple[str, str]] = []

    def fake_reset(_settings, server, seed):
        calls.append((server.server_id, seed))
        return HardcoreRun(run=1, last_alive="Cal")

    monkeypatch.setattr(trigger_daemon, "archive_and_reset", fake_reset)

    with urllib.request.urlopen(_post(base_url, "/reset/jitterbug", "1234", {"seed": "abc"})) as res:
        body = json.loads(res.read())

    assert calls == [("jitterbug", "abc")]
    assert body["status"] == "reset"
    assert body["run"]["last_alive"] == "Cal"


def test_reset_refusal_is_409_with_the_reason(
    running_daemon: tuple[str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    base_url, _ = running_daemon

    def refuse(*_args):
        raise HardcoreError("Still alive: Cal")

    monkeypatch.setattr(trigger_daemon, "archive_and_reset", refuse)

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(_post(base_url, "/reset/jitterbug", "1234", {}))

    assert exc_info.value.code == 409
    assert json.loads(exc_info.value.read()) == {"error": "Still alive: Cal"}


def test_reset_unknown_realm_returns_404(running_daemon: tuple[str, list[str]]) -> None:
    base_url, _ = running_daemon

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(_post(base_url, "/reset/nope", "1234", {}))

    assert exc_info.value.code == 404
