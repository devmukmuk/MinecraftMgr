"""Tests for scanning realm logs for gravestone placed/found events (ported from MineOps)."""

from __future__ import annotations

import gzip
from pathlib import Path

from minecraftmgr.services.gravestone_service import iter_log_files, scan_gravestones

PLACED = (
    "[12:00:01] [Server thread/INFO]: Placed MohawkBoy6's Gravestone at "
    "(10, 64, -20) in minecraft:overworld"
)
FOUND = "[12:05:01] [Server thread/INFO]: MohawkBoy6 has found their grave at (10, 64, -20)"


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    else:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_placed_grave_without_found_event_is_missing(tmp_path: Path) -> None:
    _write(tmp_path / "latest.log", [PLACED])

    result = scan_gravestones(tmp_path)

    assert len(result.placed) == 1 and len(result.missing) == 1
    grave = result.placed[0]
    assert (grave.player, grave.coord, grave.dimension) == (
        "MohawkBoy6",
        (10, 64, -20),
        "minecraft:overworld",
    )


def test_found_event_after_placed_marks_grave_found(tmp_path: Path) -> None:
    _write(tmp_path / "latest.log", [PLACED, FOUND])

    result = scan_gravestones(tmp_path)

    assert len(result.found) == 1 and not result.missing
    assert result.found[0].found_entries[0].time == "12:05:01"


def test_found_event_before_placed_is_ignored(tmp_path: Path) -> None:
    _write(tmp_path / "latest.log", [FOUND, PLACED])

    result = scan_gravestones(tmp_path)

    assert not result.found and len(result.missing) == 1


def test_found_in_a_later_log_file_counts(tmp_path: Path) -> None:
    _write(tmp_path / "2026-05-01-1.log.gz", [PLACED])
    _write(tmp_path / "latest.log", [FOUND])

    result = scan_gravestones(tmp_path)

    assert len(result.found) == 1
    assert result.found[0].file == "2026-05-01-1.log.gz"
    assert result.found[0].found_entries[0].file == "latest.log"


def test_player_filter_is_case_insensitive(tmp_path: Path) -> None:
    other = PLACED.replace("MohawkBoy6", "OtherPlayer").replace("(10, 64, -20)", "(1, 2, 3)")
    _write(tmp_path / "latest.log", [PLACED, other])

    result = scan_gravestones(tmp_path, player="mohawkboy6")

    assert [grave.player for grave in result.placed] == ["MohawkBoy6"]


def test_log_files_are_scanned_oldest_first_with_latest_last(tmp_path: Path) -> None:
    for name in ("latest.log", "2026-05-02-1.log.gz", "2026-05-01-2.log.gz", "notes.txt"):
        _write(tmp_path / name, ["x"])

    assert [path.name for path in iter_log_files(tmp_path)] == [
        "2026-05-01-2.log.gz",
        "2026-05-02-1.log.gz",
        "notes.txt",
        "latest.log",
    ]


def test_missing_folder_and_bad_gzip_become_warnings(tmp_path: Path) -> None:
    assert scan_gravestones(tmp_path / "nope").warnings

    (tmp_path / "2026-05-01-1.log.gz").write_bytes(b"not gzip")
    _write(tmp_path / "latest.log", [PLACED])

    result = scan_gravestones(tmp_path)

    assert len(result.placed) == 1
    assert "2026-05-01-1.log.gz" in result.warnings[0]
