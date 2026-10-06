"""Tests for per-realm player activity from server logs (ported from MineOps)."""

from __future__ import annotations

import gzip
import os
from datetime import date, datetime
from pathlib import Path

from typer.testing import CliRunner

from minecraftmgr.cli import app
from minecraftmgr.config.settings import Settings
from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.user_report_service import build_user_report


def _entry(server_id: str, status: str) -> ServerEntry:
    return ServerEntry(
        server_id=server_id,
        name=server_id.title(),
        status=status,
        port=26000,
        minecraft_version="26.2",
        server_type="paper",
        jar_source="",
        data_dir=f"{server_id}_dir",
        created="2026-01-01T00:00:00+00:00",
    )


def _log(settings: Settings, entry: ServerEntry, name: str, lines: list[str]) -> Path:
    path = settings.data_root / entry.data_dir / "logs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    if name.endswith(".gz"):
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


JOIN = "[12:00:01] [Server thread/INFO]: Mohawk joined the game"
LEFT = "[13:00:01] [Server thread/INFO]: Mohawk left the game"


def test_first_latest_and_days_from_dated_logs(settings: Settings) -> None:
    blue = _entry("blue", "active")
    _log(settings, blue, "2026-05-01-1.log.gz", [JOIN])
    _log(settings, blue, "2026-05-01-2.log.gz", [LEFT])
    _log(settings, blue, "2026-05-27-1.log.gz", [JOIN])

    (report,) = build_user_report(settings, [blue])

    user = report.users["Mohawk"]
    assert (user.first_seen, user.latest_seen) == (date(2026, 5, 1), date(2026, 5, 27))
    assert len(user.days_seen) == 2
    assert report.status == "active"


def test_latest_log_uses_modified_time(settings: Settings) -> None:
    blue = _entry("blue", "active")
    latest = _log(settings, blue, "latest.log", [JOIN.replace("Mohawk", "Newbie")])
    stamp = datetime(2026, 10, 2, 9, 0).timestamp()
    os.utime(latest, (stamp, stamp))

    (report,) = build_user_report(settings, [blue])

    assert report.users["Newbie"].latest_seen == date(2026, 10, 2)


def test_missing_logs_folder_is_a_warning(settings: Settings) -> None:
    (report,) = build_user_report(settings, [_entry("gone", "inactive")])

    assert report.users == {}
    assert "does not exist" in report.warnings[0]


def test_users_report_cli_groups_active_then_inactive(settings: Settings, monkeypatch) -> None:
    blue, river = _entry("blue", "active"), _entry("river", "inactive")
    _log(settings, blue, "2026-05-01-1.log.gz", [JOIN])
    monkeypatch.setattr("minecraftmgr.commands.users.load_settings", lambda: settings)
    monkeypatch.setattr(
        "minecraftmgr.commands.users.list_servers", lambda _s, **_kw: [river, blue]
    )

    result = CliRunner().invoke(app, ["users", "report"])

    assert result.exit_code == 0, result.output
    assert result.output.index("Active realms") < result.output.index("Inactive realms")
    assert "Mohawk" in result.output and "No players found" in result.output


def test_gravestones_scan_cli_needs_server_or_logs(tmp_path: Path) -> None:
    runner = CliRunner()

    assert runner.invoke(app, ["gravestones", "scan"]).exit_code == 1

    (tmp_path / "latest.log").write_text(
        "[12:00:01] [Server thread/INFO]: Placed Mohawk's Gravestone at (1, 2, 3) "
        "in minecraft:the_nether\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["gravestones", "scan", "--logs", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Not found: 1" in result.output and "(1, 2, 3)" in result.output


def test_users_report_includes_archived_realms(settings: Settings, monkeypatch) -> None:
    """Archived realms are listed last, with logs read from <data_root>/_archive/<data_dir>."""

    from dataclasses import replace

    from minecraftmgr.services.registry_service import add_server

    blue = _entry("blue", "active")
    old = replace(_entry("testrealm", "archived"), data_dir="testrealm")
    add_server(settings, blue)
    add_server(settings, old)
    _log(settings, blue, "2026-05-01-1.log.gz", [JOIN])
    archived_logs = settings.data_root / "_archive" / "testrealm" / "logs"
    archived_logs.mkdir(parents=True)
    (archived_logs / "2026-08-17-1.log").write_text(
        JOIN.replace("Mohawk", "Tester") + "\n", encoding="utf-8"
    )
    monkeypatch.setattr("minecraftmgr.commands.users.load_settings", lambda: settings)
    runner = CliRunner()

    result = runner.invoke(app, ["users", "report"])

    assert result.exit_code == 0, result.output
    assert result.output.index("Active realms") < result.output.index("Archived realms")
    assert "Tester" in result.output[result.output.index("Archived realms"):]
    assert "Archived realms" not in runner.invoke(app, ["users", "report", "--active-only"]).output


def test_players_by_realm_is_json_ready_newest_first(settings: Settings) -> None:
    """players_by_realm gives the page plain dicts, most recent player first."""

    from minecraftmgr.services.user_report_service import players_by_realm

    blue = _entry("blue", "active")
    _log(settings, blue, "2026-05-01-1.log.gz", [JOIN])
    _log(settings, blue, "2026-06-01-1.log.gz", [JOIN.replace("Mohawk", "Newer")])

    data = players_by_realm(settings, [blue])

    assert [row["player"] for row in data["blue"]] == ["Newer", "Mohawk"]
    assert data["blue"][1] == {
        "player": "Mohawk",
        "first_seen": "2026-05-01",
        "latest_seen": "2026-05-01",
        "days": 1,
        "op": False,
        "whitelisted": False,
    }


def test_rows_flag_ops_and_add_whitelisted_players_who_never_played(settings: Settings) -> None:
    """Ops are flagged; whitelisted players with no log lines follow, A-Z, once per name."""

    import json

    from minecraftmgr.services.user_report_service import players_by_realm

    blue = _entry("blue", "active")
    _log(settings, blue, "2026-05-01-1.log.gz", [JOIN])
    realm_dir = settings.data_root / blue.data_dir
    (realm_dir / "ops.json").write_text(json.dumps([{"name": "mohawk", "level": 4}]), encoding="utf-8")
    (realm_dir / "whitelist.json").write_text(
        json.dumps([{"name": "Mohawk"}, {"name": "zed"}, {"name": "Amy"}, {"name": "amy"}]),
        encoding="utf-8",
    )

    rows = players_by_realm(settings, [blue])["blue"]

    assert [(r["player"], r["op"], r["whitelisted"], r["days"]) for r in rows] == [
        ("Mohawk", True, True, 1),
        ("Amy", False, True, 0),
        ("zed", False, True, 0),
    ]
    assert rows[1]["first_seen"] is None and rows[1]["latest_seen"] is None


def test_users_report_cli_marks_ops_and_not_yet(settings: Settings, monkeypatch) -> None:
    """The terminal report shows OP next to ops and "not yet" for never-played players."""

    import json

    blue = _entry("blue", "active")
    _log(settings, blue, "2026-05-01-1.log.gz", [JOIN])
    realm_dir = settings.data_root / blue.data_dir
    (realm_dir / "ops.json").write_text(json.dumps([{"name": "Mohawk"}]), encoding="utf-8")
    (realm_dir / "whitelist.json").write_text(json.dumps([{"name": "Newbie"}]), encoding="utf-8")
    monkeypatch.setattr("minecraftmgr.commands.users.load_settings", lambda: settings)
    monkeypatch.setattr("minecraftmgr.commands.users.list_servers", lambda _s, **_kw: [blue])

    result = CliRunner().invoke(app, ["users", "report"])

    assert result.exit_code == 0, result.output
    assert "OP" in result.output and "Newbie" in result.output and "not yet" in result.output


def test_ops_who_never_played_and_are_not_whitelisted_are_listed(settings: Settings) -> None:
    """Ops can join without being whitelisted, so a never-played op still gets a row."""

    import json

    from minecraftmgr.services.user_report_service import players_by_realm

    gator = _entry("gatorland", "active")
    _log(settings, gator, "2026-08-17-1.log.gz", [JOIN.replace("Mohawk", "FourEight1516")])
    realm_dir = settings.data_root / gator.data_dir
    (realm_dir / "ops.json").write_text(
        json.dumps([{"name": "DarkNixxus"}, {"name": "FourEight1516"}]), encoding="utf-8"
    )
    (realm_dir / "whitelist.json").write_text(json.dumps([{"name": "FourEight1516"}]), encoding="utf-8")

    rows = players_by_realm(settings, [gator])["gatorland"]

    assert [(r["player"], r["op"], r["whitelisted"], r["days"]) for r in rows] == [
        ("FourEight1516", True, True, 1),
        ("DarkNixxus", True, False, 0),
    ]


def test_broken_ops_json_is_a_warning_not_silence(settings: Settings) -> None:
    """An ops.json that isn't valid JSON (e.g. a missing comma) is reported, not ignored."""

    from minecraftmgr.services.user_report_service import build_user_report

    blue = _entry("blue", "active")
    _log(settings, blue, "2026-05-01-1.log.gz", [JOIN])
    (settings.data_root / blue.data_dir / "ops.json").write_text(
        '[{"name": "a"} {"name": "b"}]', encoding="utf-8"  # missing comma
    )

    (report,) = build_user_report(settings, [blue])

    assert report.ops == set()
    assert "ops.json" in report.warnings[0] and "treated as empty" in report.warnings[0]
