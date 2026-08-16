"""Data model for the outcome of inspecting a realm's data directory."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RealmInspection:
    """What was found inspecting a realm's data directory on disk."""

    data_dir: str
    has_mods_dir: bool
    jar_path: Path | None
    jar_main_class: str | None
    detected_server_type: str
    online_mode_currently_true: bool
    current_port: int | None
    has_paper_global_yml: bool
    notes: list[str] = field(default_factory=list)
