"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from minecraftmgr.config.settings import Settings, SettingsMetadata


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Build isolated Settings pointing at a tmp_path sandbox."""

    data_root = tmp_path / "data"
    data_root.mkdir()

    return Settings(
        data_root=data_root,
        backups_root=tmp_path / "backups",
        servers_json_path=tmp_path / "servers.json",
        metadata=SettingsMetadata(
            config_path=tmp_path / "minecraftmgr.yaml",
            config_source="test",
            defaults_created=False,
        ),
    )
