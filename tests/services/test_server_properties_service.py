"""Tests for checking/fixing server.properties and Velocity trust against the standard."""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from minecraftmgr.cli import app
from minecraftmgr.config.settings import Settings
from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.registry_service import add_server
from minecraftmgr.services.server_properties_service import (
    fix_server_properties,
    fix_velocity_trust,
    load_standard,
    read_properties,
    validate_server_properties,
)

SECRET = "s3cret"
GOOD = (
    "#Minecraft server properties\n"
    "difficulty=hard\n"
    "online-mode=false\n"
    "server-ip=127.0.0.1\n"
    "server-port=26887\n"
    "white-list=true\n"
    "enforce-whitelist=true\n"
    "enable-rcon=false\n"
    "enable-query=false\n"
    "enable-jmx-monitoring=false\n"
)


def _entry(server_type: str = "paper") -> ServerEntry:
    return ServerEntry(
        server_id="jitterbug",
        name="Jitterbug",
        status="inactive",
        port=26887,
        minecraft_version="1.21.1",
        server_type=server_type,
        jar_source="",
        data_dir="jitterbug_1_21_1",
        created="2026-08-16T00:00:00+00:00",
    )


def _realm(
    root: Path, properties: str, *, velocity: dict | None = None, whitelist: str = '[{"name": "a"}]'
) -> Path:
    realm = root / "jitterbug_1_21_1"
    (realm / "config").mkdir(parents=True)
    (realm / "server.properties").write_bytes(properties.encode("utf-8"))
    (realm / "whitelist.json").write_text(whitelist, encoding="utf-8")
    if velocity is None:
        velocity = {"enabled": True, "online-mode": True, "secret": SECRET}
    (realm / "config" / "paper-global.yml").write_text(
        yaml.safe_dump({"proxies": {"velocity": velocity}, "misc": {"keep": 1}}), encoding="utf-8"
    )
    return realm


def test_standard_has_port_substituted_and_reasons() -> None:
    """The standard file's __PORT__ is filled in and every key has a reason."""

    standard = {s.key: s for s in load_standard(26887)}

    assert standard["server-port"].value == "26887"
    assert standard["white-list"].value == "true"
    assert "127.0.0.1" not in standard["server-ip"].reason  # reason is the comment, not the value
    assert standard["server-ip"].reason.startswith("Only Velocity")
    assert all(s.reason for s in standard.values())


def test_realm_at_standard_is_ok(tmp_path: Path) -> None:
    """A realm matching the standard with a valid Velocity block is OK."""

    result = validate_server_properties(_realm(tmp_path, GOOD), _entry(), velocity_secret=SECRET)

    assert result.ok and not result.warnings


def test_differences_and_missing_keys_are_reported(tmp_path: Path) -> None:
    """Wrong values and missing keys are both issues."""

    props = GOOD.replace("white-list=true", "white-list=false").replace("enable-query=false\n", "")
    result = validate_server_properties(_realm(tmp_path, props), _entry(), velocity_secret=SECRET)

    found = {issue.key: issue.current for issue in result.issues}
    assert found == {"white-list": "false", "enable-query": None}


def test_wrong_port_is_reported(tmp_path: Path) -> None:
    """server-port must match the servers.json port."""

    result = validate_server_properties(
        _realm(tmp_path, GOOD.replace("26887", "26111")), _entry(), velocity_secret=SECRET
    )

    issues = [(i.key, i.current, i.expected) for i in result.issues]
    assert issues == [("server-port", "26111", "26887")]


def test_fix_changes_only_standard_keys_in_place(tmp_path: Path) -> None:
    """Fixing keeps other lines, order and CRLF endings; missing keys are appended."""

    props = GOOD.replace("white-list=true", "white-list=false").replace("enable-query=false\n", "")
    realm = _realm(tmp_path, props.replace("\n", "\r\n"))
    result = validate_server_properties(realm, _entry(), velocity_secret=SECRET)

    fix_server_properties(realm, result.issues)

    raw = (realm / "server.properties").read_bytes()
    assert b"\r\n" in raw and b"\n\n" not in raw.replace(b"\r\n", b"")
    lines = raw.decode().splitlines()
    assert lines[0] == "#Minecraft server properties" and lines[1] == "difficulty=hard"
    assert lines.index("white-list=true") == 5
    assert lines[-1] == "enable-query=false"
    assert validate_server_properties(realm, _entry(), velocity_secret=SECRET).ok


def test_velocity_trust_problems_and_fix(tmp_path: Path) -> None:
    """Velocity trust problems never show the secret, and the fix keeps the rest of the file."""

    velocity = {"enabled": False, "online-mode": True, "secret": "old"}
    realm = _realm(tmp_path, GOOD, velocity=velocity)
    result = validate_server_properties(realm, _entry(), velocity_secret=SECRET)

    assert len(result.velocity_issues) == 2 and not result.ok
    assert all(SECRET not in problem and "old" not in problem for problem in result.velocity_issues)

    fix_velocity_trust(realm, SECRET)

    data = yaml.safe_load((realm / "config" / "paper-global.yml").read_text(encoding="utf-8"))
    assert data["proxies"]["velocity"] == {"enabled": True, "online-mode": True, "secret": SECRET}
    assert data["misc"] == {"keep": 1}


def test_non_paper_realm_skips_velocity_check(tmp_path: Path) -> None:
    """Only Paper realms have a paper-global.yml to check."""

    realm = _realm(tmp_path, GOOD, velocity={})

    assert validate_server_properties(realm, _entry("fabric"), velocity_secret=SECRET).ok


def test_empty_whitelist_is_a_warning(tmp_path: Path) -> None:
    """white-list=true with an empty whitelist.json warns that nobody can join."""

    realm = _realm(tmp_path, GOOD, whitelist="[]")
    result = validate_server_properties(realm, _entry(), velocity_secret=SECRET)

    assert result.ok and "nobody can join" in result.warnings[0]


def test_read_properties_first_occurrence_wins(tmp_path: Path) -> None:
    """Values may contain '=' and the first occurrence of a key wins."""

    path = tmp_path / "server.properties"
    path.write_text("# c\nmotd=a=b\nmotd=second\n", encoding="utf-8")

    assert read_properties(path) == {"motd": "a=b"}


def test_validate_cli_reports_then_fixes_with_yes(settings: Settings, monkeypatch) -> None:
    """validate reports, --fix asks first, and --fix --yes applies the standard."""

    add_server(settings, _entry())
    realm = _realm(settings.data_root, GOOD.replace("white-list=true", "white-list=false"))
    (realm / "start.sh").write_text(
        "#!/bin/bash\nPORT=26887\njava -Djava.net.preferIPv4Stack=true -jar x.jar\n", encoding="utf-8"
    )
    (settings.data_root / "_proxy").mkdir()
    (settings.data_root / "_proxy" / "forwarding.secret").write_text(SECRET + "\n", encoding="utf-8")
    monkeypatch.setattr("minecraftmgr.commands.realm.load_settings", lambda: settings)
    runner = CliRunner()

    report = runner.invoke(app, ["validate", "jitterbug"])
    assert report.exit_code == 1, report.output
    assert "white-list" in report.output and "false" in report.output

    declined = runner.invoke(app, ["realm", "validate", "jitterbug", "--fix"], input="n\n")
    assert "Skipped" in declined.output
    assert read_properties(realm / "server.properties")["white-list"] == "false"

    fixed = runner.invoke(app, ["realm", "validate", "jitterbug", "--fix", "--yes"])
    assert fixed.exit_code == 0, fixed.output
    assert read_properties(realm / "server.properties")["white-list"] == "true"
    assert "OK" in runner.invoke(app, ["validate", "jitterbug"]).output
