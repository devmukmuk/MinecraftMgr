"""Tests for realm engine detection -- positive identification, not folder-shape guessing."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from minecraftmgr.services.realm_inspect_service import (
    IncompatibleRealmError,
    inspect_realm_dir,
    is_velocity_compatible,
    require_velocity_compatible,
)


def _make_jar(path: Path, main_class: str | None) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        if main_class is not None:
            archive.writestr("META-INF/MANIFEST.MF", f"Manifest-Version: 1.0\nMain-Class: {main_class}\n")


def test_detects_paper_via_paperclip_main_class(tmp_path: Path) -> None:
    """A jar with a Paperclip Main-Class is positively detected as paper."""

    realm_dir = tmp_path / "gravestone"
    realm_dir.mkdir()
    _make_jar(realm_dir / "server_gravestone.jar", "io.papermc.paperclip.Paperclip")

    inspection = inspect_realm_dir(realm_dir)

    assert inspection.detected_server_type == "paper"
    assert is_velocity_compatible(inspection) is True


def test_detects_vanilla_even_with_no_mods_dir(tmp_path: Path) -> None:
    """No mods/ dir does NOT imply Paper -- vanilla is caught by its own Main-Class.

    This is the exact bug hit with jitterbug: no mods/ dir, but still vanilla
    and incompatible with Velocity forwarding.
    """

    realm_dir = tmp_path / "jitterbug"
    realm_dir.mkdir()
    _make_jar(realm_dir / "server_jitterbug.jar", "net.minecraft.bundler.Main")

    inspection = inspect_realm_dir(realm_dir)

    assert inspection.has_mods_dir is False
    assert inspection.detected_server_type == "vanilla"
    assert is_velocity_compatible(inspection) is False


def test_detects_fabric_via_main_class(tmp_path: Path) -> None:
    """A fabricmc Main-Class is detected as fabric."""

    realm_dir = tmp_path / "arbor"
    realm_dir.mkdir()
    (realm_dir / "mods").mkdir()
    _make_jar(realm_dir / "server_arbor.jar", "net.fabricmc.loader.impl.launch.knot.KnotServer")

    inspection = inspect_realm_dir(realm_dir)

    assert inspection.has_mods_dir is True
    assert inspection.detected_server_type == "fabric"
    assert is_velocity_compatible(inspection) is False


def test_detects_forge_via_bootstraplauncher(tmp_path: Path) -> None:
    """A modern Forge bootstrap Main-Class is detected as forge."""

    realm_dir = tmp_path / "modded"
    realm_dir.mkdir()
    _make_jar(realm_dir / "server_modded.jar", "cpw.mods.bootstraplauncher.BootstrapLauncher")

    inspection = inspect_realm_dir(realm_dir)

    assert inspection.detected_server_type == "forge"


def test_unknown_when_no_jar_present(tmp_path: Path) -> None:
    """No server_*.jar at all is 'unknown', with a note, not a guess."""

    realm_dir = tmp_path / "empty_realm"
    realm_dir.mkdir()

    inspection = inspect_realm_dir(realm_dir)

    assert inspection.detected_server_type == "unknown"
    assert inspection.jar_path is None
    assert any("No server_*.jar" in note for note in inspection.notes)


def test_mods_dir_present_but_not_fabric_detected_adds_a_note(tmp_path: Path) -> None:
    """A mods/ dir with a non-fabric-detected jar gets flagged for suspicion, not silently trusted."""

    realm_dir = tmp_path / "weird"
    realm_dir.mkdir()
    (realm_dir / "mods").mkdir()
    _make_jar(realm_dir / "server_weird.jar", "io.papermc.paperclip.Paperclip")

    inspection = inspect_realm_dir(realm_dir)

    assert any("mods/" in note for note in inspection.notes)


def test_reads_online_mode_and_port_from_server_properties(tmp_path: Path) -> None:
    """server.properties fields are parsed for online-mode and server-port."""

    realm_dir = tmp_path / "river"
    realm_dir.mkdir()
    (realm_dir / "server.properties").write_text(
        "online-mode=true\nserver-port=26010\n", encoding="utf-8"
    )

    inspection = inspect_realm_dir(realm_dir)

    assert inspection.online_mode_currently_true is True
    assert inspection.current_port == 26010


def test_has_paper_global_yml_detected(tmp_path: Path) -> None:
    """config/paper-global.yml presence is reported (only exists after a first boot)."""

    realm_dir = tmp_path / "cave"
    realm_dir.mkdir()
    (realm_dir / "config").mkdir()
    (realm_dir / "config" / "paper-global.yml").write_text("proxies: {}", encoding="utf-8")

    inspection = inspect_realm_dir(realm_dir)

    assert inspection.has_paper_global_yml is True


def test_require_velocity_compatible_passes_for_paper(tmp_path: Path) -> None:
    """A Paper realm passes the compatibility gate without raising."""

    realm_dir = tmp_path / "gravestone"
    realm_dir.mkdir()
    _make_jar(realm_dir / "server_gravestone.jar", "io.papermc.paperclip.Paperclip")

    require_velocity_compatible(inspect_realm_dir(realm_dir))


def test_require_velocity_compatible_raises_for_vanilla_naming_the_type(tmp_path: Path) -> None:
    """A non-Paper realm raises IncompatibleRealmError naming what was actually detected."""

    realm_dir = tmp_path / "jitterbug"
    realm_dir.mkdir()
    _make_jar(realm_dir / "server_jitterbug.jar", "net.minecraft.bundler.Main")

    with pytest.raises(IncompatibleRealmError, match="vanilla"):
        require_velocity_compatible(inspect_realm_dir(realm_dir))
