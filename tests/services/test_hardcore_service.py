"""Tests for hardcore run summaries and Archive & Reset."""

from __future__ import annotations

import gzip
import json
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from minecraftmgr.config.settings import Settings
from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.hardcore_service import (
    RUNS_FILE_NAME,
    HardcoreError,
    archive_and_reset,
    build_run_summary,
    clean_seed,
    hardcore_report,
    load_runs,
)
from minecraftmgr.services.server_properties_service import read_properties

UUIDS = {"Amy": "uuid-amy", "Bob": "uuid-bob", "Cal": "uuid-cal"}


def _entry(mode: str = "hardcore") -> ServerEntry:
    return ServerEntry(
        server_id="hardcore",
        name="Hardcore",
        status="active",
        port=26666,
        minecraft_version="26.2",
        server_type="paper",
        jar_source="",
        data_dir="hardcore",
        created="2026-10-30T00:00:00+00:00",
        mode=mode,
    )


def _stats(realm_dir: Path, player: str, *, seconds: int, deaths: int = 0) -> None:
    stats_dir = realm_dir / "world" / "stats"
    stats_dir.mkdir(parents=True, exist_ok=True)
    custom = {"minecraft:play_time": seconds * 20, "minecraft:deaths": deaths}
    (stats_dir / f"{UUIDS[player]}.json").write_text(
        json.dumps({"stats": {"minecraft:custom": custom}, "DataVersion": 4000}), encoding="utf-8"
    )


def _realm(root: Path, *, everyone_dead: bool = True) -> Path:
    """A hardcore realm folder: Amy and Bob die on day one, Cal dies after midnight on day two."""

    realm_dir = root / "hardcore"
    (realm_dir / "logs").mkdir(parents=True)
    (realm_dir / "world_nether").mkdir()
    (realm_dir / "plugins").mkdir()
    (realm_dir / "server.properties").write_text(
        "hardcore=true\nlevel-seed=12345\nserver-port=26666\n", encoding="utf-8"
    )
    (realm_dir / "usercache.json").write_text(
        json.dumps([{"name": name, "uuid": uuid} for name, uuid in UUIDS.items()]), encoding="utf-8"
    )

    day_one = (
        "[19:00:01 INFO]: Amy joined the game\n"
        "[19:00:05 INFO]: Bob joined the game\n"
        "[19:30:00 INFO]: <Amy> Bob was here\n"
        "[19:40:00 INFO]: Bob has made the advancement [Stone Age]\n"
        "[20:15:42 INFO]: Amy was slain by Zombie\n"
        "[20:20:00 INFO]: Bob was kicked for floating too long!\n"
        "[21:02:10 INFO]: Bob fell from a high place\n"
        "[21:05:00 INFO]: Amy left the game\n"
    )
    with gzip.open(realm_dir / "logs" / "2026-10-28-1.log.gz", "wt", encoding="utf-8") as handle:
        handle.write(day_one)

    cal = "[23:59:00] [Server thread/INFO]: Cal joined the game\n"
    if everyone_dead:
        cal += "[00:10:30] [Server thread/INFO]: Cal tried to swim in lava\n"
    with gzip.open(realm_dir / "logs" / "2026-10-29-1.log.gz", "wt", encoding="utf-8") as handle:
        handle.write(cal)

    _stats(realm_dir, "Amy", seconds=4500, deaths=1)
    _stats(realm_dir, "Bob", seconds=7300, deaths=1)
    _stats(realm_dir, "Cal", seconds=600, deaths=1 if everyone_dead else 0)
    return realm_dir


def _no_screen(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, 0, stdout="No Sockets found.\n", stderr="")


def test_summary_orders_deaths_and_names_last_alive(tmp_path: Path) -> None:
    """Deaths come from the logs in time order (across midnight); play time from stats."""

    run = build_run_summary(_realm(tmp_path))

    assert [p.player for p in run.players] == ["Amy", "Bob", "Cal"]
    assert [p.death_order for p in run.players] == [1, 2, 3]
    assert run.players[0].death_message == "Amy was slain by Zombie"
    assert run.players[1].play_seconds == 7300
    assert run.players[2].died_at == "2026-10-30T00:10:30"
    assert run.started_at == "2026-10-28T19:00:01"
    assert run.ended_at == "2026-10-30T00:10:30"
    assert run.last_alive == "Cal"
    assert run.everyone_dead


def test_summary_ignores_chat_advancements_and_kicks(tmp_path: Path) -> None:
    """Chat, advancements and kicks that start with a player's name aren't deaths."""

    run = build_run_summary(_realm(tmp_path))

    assert run.players[1].death_message == "Bob fell from a high place"


def test_summary_with_a_survivor_is_not_over(tmp_path: Path) -> None:
    run = build_run_summary(_realm(tmp_path, everyone_dead=False))

    assert run.alive == ["Cal"]
    assert not run.everyone_dead
    assert run.last_alive is None
    assert run.to_dict()["everyone_dead"] is False


def test_summary_counts_a_stats_death_missing_from_the_logs(tmp_path: Path) -> None:
    realm_dir = _realm(tmp_path, everyone_dead=False)
    _stats(realm_dir, "Cal", seconds=600, deaths=1)

    run = build_run_summary(realm_dir)

    assert run.everyone_dead
    assert run.players[-1].player == "Cal" and run.players[-1].death_order is None
    assert run.last_alive == "Bob"


def test_summary_of_a_fresh_world_is_empty(tmp_path: Path) -> None:
    realm_dir = tmp_path / "hardcore"
    realm_dir.mkdir()

    run = build_run_summary(realm_dir)

    assert run.players == []
    assert not run.everyone_dead


def test_archive_and_reset_archives_clears_world_and_sets_seed(settings: Settings) -> None:
    realm_dir = _realm(settings.data_root)
    when = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)

    run = archive_and_reset(settings, _entry(), "  my seed  ", runner=_no_screen, now=lambda: when)

    assert run.run == 1
    assert run.seed == "12345"
    assert run.last_alive == "Cal"
    archive = settings.backups_root / "hardcore" / "hardcore" / "hardcore-run1-20261030T120000Z.tar.gz"
    assert run.archive == archive.name
    with tarfile.open(archive) as tar:
        names = tar.getnames()
    assert "world/stats/uuid-amy.json" in names
    assert "logs/2026-10-28-1.log.gz" in names
    assert archive.with_name(archive.name + ".sha256").is_file()

    assert not (realm_dir / "world").exists()
    assert not (realm_dir / "world_nether").exists()
    assert not (realm_dir / "logs").exists()
    assert (realm_dir / "plugins").is_dir()
    assert (realm_dir / "usercache.json").is_file()
    assert read_properties(realm_dir / "server.properties")["level-seed"] == "my seed"
    assert read_properties(realm_dir / "server.properties")["hardcore"] == "true"

    runs = load_runs(realm_dir)
    assert len(runs) == 1 and runs[0]["last_alive"] == "Cal"


def test_second_reset_appends_run_and_blank_seed_is_random(settings: Settings) -> None:
    realm_dir = _realm(settings.data_root)
    archive_and_reset(settings, _entry(), "", runner=_no_screen)
    assert read_properties(realm_dir / "server.properties")["level-seed"] == ""

    (realm_dir / "logs").mkdir()
    (realm_dir / "logs" / "latest.log").write_text(
        "[10:00:00 INFO]: Bob joined the game\n[10:30:00 INFO]: Bob drowned\n", encoding="utf-8"
    )
    run = archive_and_reset(settings, _entry(), "", runner=_no_screen)

    assert run.run == 2
    assert run.seed == "random"
    assert run.last_alive == "Bob"
    assert [r["run"] for r in load_runs(realm_dir)] == [1, 2]


def test_reset_refused_while_anyone_is_alive(settings: Settings) -> None:
    realm_dir = _realm(settings.data_root, everyone_dead=False)

    with pytest.raises(HardcoreError, match="Still alive: Cal"):
        archive_and_reset(settings, _entry(), "", runner=_no_screen)

    assert (realm_dir / "world").is_dir()
    assert not (realm_dir / RUNS_FILE_NAME).exists()


def test_reset_refused_before_anyone_has_played(settings: Settings) -> None:
    realm_dir = settings.data_root / "hardcore"
    realm_dir.mkdir()
    (realm_dir / "server.properties").write_text("hardcore=true\n", encoding="utf-8")

    with pytest.raises(HardcoreError, match="No one has played"):
        archive_and_reset(settings, _entry(), "", runner=_no_screen)


def test_reset_refused_for_a_survival_realm(settings: Settings) -> None:
    _realm(settings.data_root)

    with pytest.raises(HardcoreError, match="not a hardcore realm"):
        archive_and_reset(settings, _entry(mode="survival"), "", runner=_no_screen)


def test_reset_stops_a_running_realm_first(settings: Settings) -> None:
    _realm(settings.data_root)
    calls: list[list[str]] = []
    running = {"up": True}

    def runner(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[:2] == ["screen", "-S"]:
            running["up"] = False
        stdout = "\t123.hardcore\t(Detached)\n" if running["up"] else "No Sockets found.\n"
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    archive_and_reset(settings, _entry(), "", runner=runner)

    assert ["screen", "-S", "hardcore", "-p", "0", "-X", "stuff", "stop\r"] in calls


@pytest.mark.parametrize("seed", ["a\nb", "x" * 65, "back\\slash"])
def test_clean_seed_rejects_unsafe_seeds(seed: str) -> None:
    with pytest.raises(HardcoreError):
        clean_seed(seed)


def test_hardcore_report_covers_only_hardcore_realms(settings: Settings) -> None:
    _realm(settings.data_root)
    survival = ServerEntry(**{**_entry().__dict__, "server_id": "gatorland", "mode": "survival"})

    report = hardcore_report(settings, [_entry(), survival])

    assert list(report) == ["hardcore"]
    assert report["hardcore"]["current"]["last_alive"] == "Cal"
    assert report["hardcore"]["runs"] == []


def test_summary_reads_the_26_3_log_prefix_and_players_stats_folder(tmp_path: Path) -> None:
    """26.3 writes "System chat: " before join/death lines and keeps stats in world/players/stats."""

    realm_dir = tmp_path / "hardcore"
    (realm_dir / "logs").mkdir(parents=True)
    (realm_dir / "usercache.json").write_text(
        json.dumps([{"name": "Amy", "uuid": UUIDS["Amy"]}]), encoding="utf-8"
    )
    (realm_dir / "logs" / "2026-10-30-1.log.gz").write_bytes(gzip.compress(
        b"[09:25:08] [Server thread/INFO]: System chat: Amy joined the game\n"
        b"[09:25:08] [Server thread/INFO]: Amy[/192.168.1.68:39870] logged in with entity id 1223\n"
        b"[09:31:33] [Server thread/INFO]: System chat: Amy was shot by Skeleton\n"
        b"[09:31:39] [Server thread/INFO]: System chat: Amy left the game\n"
    ))
    stats_dir = realm_dir / "world" / "players" / "stats"
    stats_dir.mkdir(parents=True)
    (stats_dir / f"{UUIDS['Amy']}.json").write_text(
        json.dumps({"stats": {"minecraft:custom": {"minecraft:play_time": 10251, "minecraft:deaths": 1}}}),
        encoding="utf-8",
    )

    run = build_run_summary(realm_dir)

    assert [p.player for p in run.players] == ["Amy"]
    assert run.players[0].death_message == "Amy was shot by Skeleton"
    assert run.players[0].play_seconds == 512
    assert run.everyone_dead and run.last_alive == "Amy"


def test_stats_alone_count_a_player_on_the_26_3_layout(tmp_path: Path) -> None:
    """With no usable log lines, the players/stats files still list the player and their death."""

    realm_dir = tmp_path / "hardcore"
    realm_dir.mkdir()
    (realm_dir / "usercache.json").write_text(
        json.dumps([{"name": "Amy", "uuid": UUIDS["Amy"]}]), encoding="utf-8"
    )
    stats_dir = realm_dir / "world" / "players" / "stats"
    stats_dir.mkdir(parents=True)
    (stats_dir / f"{UUIDS['Amy']}.json").write_text(
        json.dumps({"stats": {"minecraft:custom": {"minecraft:deaths": 1}}}), encoding="utf-8"
    )

    run = build_run_summary(realm_dir)

    assert run.everyone_dead
    assert run.players[0].player == "Amy"
