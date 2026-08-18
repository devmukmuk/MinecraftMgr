"""Tests for validating and fixing a realm's start.sh against the canonical template."""

from __future__ import annotations

from pathlib import Path

from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.realm_validate_service import fix_start_sh, validate_start_sh


def _entry(server_id: str, data_dir: str, port: int = 26005) -> ServerEntry:
    return ServerEntry(
        server_id=server_id,
        name=server_id.title(),
        status="active",
        port=port,
        minecraft_version="1.21.10",
        server_type="paper",
        jar_source="",
        data_dir=data_dir,
        created="2026-08-15T21:00:00+00:00",
        notes="",
    )


_GOOD_START_SH = """#!/bin/bash
set -u
umask 0027
cd "$(dirname "$0")" || exit 1

NAME="gravestone"
PORT=26005
MEM_MIN="2G"
MEM_MAX="4G"
JAR="server_${NAME}.jar"

exec java -Djava.net.preferIPv4Stack=true -Xms$MEM_MIN -Xmx$MEM_MAX -jar "$JAR" nogui --port $PORT
"""

_MISSING_IPV4_START_SH = """#!/bin/bash
umask 0027
cd "$(dirname "$0")"

NAME="arbor_1_21_10"
PORT=26124
MEM_MIN="2G"
MEM_MAX="14G"
JAR="server_${NAME}.jar"

java -Xms$MEM_MIN -Xmx$MEM_MAX -jar "$JAR" nogui --port $PORT
"""


def test_validate_ok_for_a_conformant_start_sh(tmp_path: Path) -> None:
    """A start.sh with the IPv4 flag and a matching port reports no issues."""

    realm_dir = tmp_path / "gravestone"
    realm_dir.mkdir()
    (realm_dir / "start.sh").write_text(_GOOD_START_SH, encoding="utf-8")

    entry = _entry("gravestone", "gravestone", port=26005)
    result = validate_start_sh(realm_dir, entry)

    assert result.ok is True
    assert result.issues == []


def test_validate_flags_missing_ipv4_stack_flag(tmp_path: Path) -> None:
    """A start.sh without -Djava.net.preferIPv4Stack=true is flagged."""

    realm_dir = tmp_path / "arbor_1_21_10"
    realm_dir.mkdir()
    (realm_dir / "start.sh").write_text(_MISSING_IPV4_START_SH, encoding="utf-8")

    entry = _entry("arbor", "arbor_1_21_10", port=26124)
    result = validate_start_sh(realm_dir, entry)

    assert result.ok is False
    assert result.has_ipv4_flag is False
    assert any("preferIPv4Stack" in issue for issue in result.issues)


def test_validate_flags_port_mismatch(tmp_path: Path) -> None:
    """A start.sh PORT= that disagrees with the registry's port is flagged."""

    realm_dir = tmp_path / "gravestone"
    realm_dir.mkdir()
    (realm_dir / "start.sh").write_text(_GOOD_START_SH, encoding="utf-8")

    entry = _entry("gravestone", "gravestone", port=9999)
    result = validate_start_sh(realm_dir, entry)

    assert result.ok is False
    assert result.port_matches_registry is False
    assert any("does not match" in issue for issue in result.issues)


def test_validate_reports_missing_start_sh(tmp_path: Path) -> None:
    """A realm dir with no start.sh at all is reported as not existing, not crashed on."""

    realm_dir = tmp_path / "gatorland_26_2"
    realm_dir.mkdir()

    entry = _entry("gatorland", "gatorland_26_2", port=26788)
    result = validate_start_sh(realm_dir, entry)

    assert result.exists is False
    assert result.ok is False
    assert "start.sh does not exist" in result.issues


def test_validate_captures_current_mem_settings(tmp_path: Path) -> None:
    """MEM_MIN/MEM_MAX are read from the file but never judged -- just carried through."""

    realm_dir = tmp_path / "arbor_1_21_10"
    realm_dir.mkdir()
    (realm_dir / "start.sh").write_text(_MISSING_IPV4_START_SH, encoding="utf-8")

    entry = _entry("arbor", "arbor_1_21_10", port=26124)
    result = validate_start_sh(realm_dir, entry)

    assert result.current_mem_min == "2G"
    assert result.current_mem_max == "14G"


def test_fix_rewrites_start_sh_preserving_existing_mem_settings(tmp_path: Path) -> None:
    """--fix regenerates from the canonical template, keeping the file's own mem values."""

    realm_dir = tmp_path / "arbor_1_21_10"
    realm_dir.mkdir()
    (realm_dir / "start.sh").write_text(_MISSING_IPV4_START_SH, encoding="utf-8")

    entry = _entry("arbor", "arbor_1_21_10", port=26124)
    before = validate_start_sh(realm_dir, entry)

    fix_start_sh(realm_dir, entry, before)

    after = validate_start_sh(realm_dir, entry)
    assert after.ok is True
    assert after.current_mem_min == "2G"
    assert after.current_mem_max == "14G"  # preserved, not silently "fixed"


def test_fix_falls_back_to_defaults_when_mem_settings_were_never_present(tmp_path: Path) -> None:
    """A validation with no captured mem values (e.g. missing start.sh) falls back to defaults."""

    realm_dir = tmp_path / "gatorland_26_2"
    realm_dir.mkdir()

    entry = _entry("gatorland", "gatorland_26_2", port=26788)
    validation = validate_start_sh(realm_dir, entry)

    fix_start_sh(realm_dir, entry, validation)

    rendered = (realm_dir / "start.sh").read_text(encoding="utf-8")
    assert 'MEM_MIN="2G"' in rendered
    assert 'MEM_MAX="4G"' in rendered
