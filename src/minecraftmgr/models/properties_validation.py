"""Data models for checking a realm's server.properties against the standard settings."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StandardSetting:
    """One key=value from tools/templates/server.properties.standard, with why it matters."""

    key: str
    value: str
    reason: str


@dataclass(frozen=True)
class PropertyIssue:
    """A server.properties key that differs from the standard (current None = missing)."""

    key: str
    current: str | None
    expected: str
    reason: str


@dataclass
class PropertiesValidation:
    """Result of checking one realm's server.properties and Velocity trust config."""

    data_dir: str
    exists: bool
    issues: list[PropertyIssue] = field(default_factory=list)
    velocity_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return whether there is nothing to fix."""

        return self.exists and not self.issues and not self.velocity_issues
