"""Data models for a hardcore realm's run summary (who played, how long, who died when)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class HardcorePlayer:
    """One player's part in a hardcore run."""

    player: str
    play_seconds: int | None = None
    died_at: str | None = None
    death_message: str | None = None
    dead: bool = False
    death_order: int | None = None


@dataclass
class HardcoreRun:
    """A hardcore run: the current one (built live from logs/stats) or an archived one."""

    players: list[HardcorePlayer] = field(default_factory=list)
    started_at: str | None = None
    ended_at: str | None = None
    last_alive: str | None = None
    run: int | None = None
    seed: str | None = None
    reset_at: str | None = None
    archive: str | None = None

    @property
    def everyone_dead(self) -> bool:
        """True once at least one player has joined and every player has died."""

        return bool(self.players) and all(player.dead for player in self.players)

    @property
    def alive(self) -> list[str]:
        return [player.player for player in self.players if not player.dead]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["everyone_dead"] = self.everyone_dead
        return data
