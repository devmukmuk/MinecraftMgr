"""Data model for the outcome of validating a realm's start.sh."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StartShValidation:
    """What was found checking a realm's start.sh against the canonical template."""

    data_dir: str
    exists: bool
    has_ipv4_flag: bool
    port_matches_registry: bool
    current_mem_min: str | None
    current_mem_max: str | None
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.exists and not self.issues
