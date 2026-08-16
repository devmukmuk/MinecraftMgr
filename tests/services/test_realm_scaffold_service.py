"""Tests for scaffolding a brand-new realm's data directory."""

from __future__ import annotations

from pathlib import Path

import pytest

from minecraftmgr.services.realm_scaffold_service import (
    EMPTY_ARRAY_CONTROL_FILES,
    REALM_SUBDIRS,
    ScaffoldError,
    scaffold_realm_dir,
)


@pytest.fixture
def fake_jar(tmp_path: Path) -> Path:
    jar_path = tmp_path / "source_server.jar"
    jar_path.write_bytes(b"fake paper jar contents")
    return jar_path


def test_scaffold_creates_expected_subdirs(tmp_path: Path, fake_jar: Path) -> None:
    """Every standard realm subdirectory gets created."""

    realm_dir = tmp_path / "gatorland"

    scaffold_realm_dir(realm_dir, jar_path=fake_jar, data_dir="gatorland", port=26020)

    for subdir in REALM_SUBDIRS:
        assert (realm_dir / subdir).is_dir()


def test_scaffold_writes_empty_array_control_files(tmp_path: Path, fake_jar: Path) -> None:
    """Control files (bans/ops/whitelist/usercache) are created as empty JSON arrays."""

    realm_dir = tmp_path / "gatorland"

    scaffold_realm_dir(realm_dir, jar_path=fake_jar, data_dir="gatorland", port=26020)

    for filename in EMPTY_ARRAY_CONTROL_FILES:
        assert (realm_dir / filename).read_text(encoding="utf-8") == "[]"


def test_scaffold_writes_eula_true(tmp_path: Path, fake_jar: Path) -> None:
    """eula.txt agrees to the EULA."""

    realm_dir = tmp_path / "gatorland"

    scaffold_realm_dir(realm_dir, jar_path=fake_jar, data_dir="gatorland", port=26020)

    assert "eula=true" in (realm_dir / "eula.txt").read_text(encoding="utf-8")


def test_scaffold_writes_velocity_ready_server_properties(tmp_path: Path, fake_jar: Path) -> None:
    """server.properties is written Velocity-ready from the start -- no separate patch step."""

    realm_dir = tmp_path / "gatorland"

    scaffold_realm_dir(realm_dir, jar_path=fake_jar, data_dir="gatorland", port=26020)

    properties = (realm_dir / "server.properties").read_text(encoding="utf-8")

    assert "server-port=26020" in properties
    assert "server-ip=127.0.0.1" in properties
    assert "online-mode=false" in properties


def test_scaffold_renders_start_sh_with_substitutions(tmp_path: Path, fake_jar: Path) -> None:
    """start.sh is rendered from the real template with NAME/PORT/MEM substituted correctly."""

    realm_dir = tmp_path / "gatorland"

    scaffold_realm_dir(
        realm_dir,
        jar_path=fake_jar,
        data_dir="gatorland",
        port=26020,
        mem_min="3G",
        mem_max="10G",
    )

    start_sh = (realm_dir / "start.sh").read_text(encoding="utf-8")

    assert 'NAME="gatorland"' in start_sh
    assert "PORT=26020" in start_sh
    assert 'MEM_MIN="3G"' in start_sh
    assert 'MEM_MAX="10G"' in start_sh
    assert "-Djava.net.preferIPv4Stack=true" in start_sh
    assert "__" not in start_sh  # no leftover unreplaced placeholder tokens


def test_scaffold_copies_jar_with_data_dir_name(tmp_path: Path, fake_jar: Path) -> None:
    """The supplied jar is copied in as server_<data_dir>.jar."""

    realm_dir = tmp_path / "gatorland"

    scaffold_realm_dir(realm_dir, jar_path=fake_jar, data_dir="gatorland", port=26020)

    copied = realm_dir / "server_gatorland.jar"
    assert copied.read_bytes() == fake_jar.read_bytes()


def test_scaffold_refuses_non_empty_dir_without_force(tmp_path: Path, fake_jar: Path) -> None:
    """A non-empty target directory is refused unless force=True."""

    realm_dir = tmp_path / "gatorland"
    realm_dir.mkdir()
    (realm_dir / "leftover.txt").write_text("something already here", encoding="utf-8")

    with pytest.raises(ScaffoldError):
        scaffold_realm_dir(realm_dir, jar_path=fake_jar, data_dir="gatorland", port=26020)


def test_scaffold_allows_non_empty_dir_with_force(tmp_path: Path, fake_jar: Path) -> None:
    """force=True proceeds even against a non-empty target directory."""

    realm_dir = tmp_path / "gatorland"
    realm_dir.mkdir()
    (realm_dir / "leftover.txt").write_text("something already here", encoding="utf-8")

    scaffold_realm_dir(realm_dir, jar_path=fake_jar, data_dir="gatorland", port=26020, force=True)

    assert (realm_dir / "server_gatorland.jar").exists()
