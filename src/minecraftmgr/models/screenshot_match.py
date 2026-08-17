"""Data model for a screenshot matched (or not) to a realm session."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ScreenshotMatch:
    """Outcome of matching one screenshot file to a realm session."""

    filename: str
    taken_at: datetime | None
    realm: str | None
    minecraft_version: str | None
    relative_path: str
    matched: bool

    def to_dict(self) -> dict:
        """Return the manifest.json field shape for this match."""

        return {
            "filename": self.filename,
            "taken_at": self.taken_at.isoformat() if self.taken_at else None,
            "realm": self.realm,
            "minecraft_version": self.minecraft_version,
            "relative_path": self.relative_path,
            "matched": self.matched,
        }

    @staticmethod
    def from_dict(data: dict) -> "ScreenshotMatch":
        """Build a ScreenshotMatch from a manifest.json entry dict."""

        taken_at = data.get("taken_at")

        return ScreenshotMatch(
            filename=str(data["filename"]),
            taken_at=datetime.fromisoformat(taken_at) if taken_at else None,
            realm=data.get("realm"),
            minecraft_version=data.get("minecraft_version"),
            relative_path=str(data["relative_path"]),
            matched=bool(data["matched"]),
        )
