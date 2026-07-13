from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.shared.actions import GameAction


COMMAND_SCHEMA_VERSION = 1


def command_id_for(actor_id: str, sequence: int) -> str:
    """Build a stable transport id without consuming gameplay RNG or entity ids."""

    actor_key = str(actor_id).encode("utf-8").hex() or "00"
    return f"command-{actor_key}-{max(0, int(sequence)):012d}"


@dataclass(frozen=True)
class CommandEnvelope:
    command_id: str
    actor_id: str
    sequence: int
    action: GameAction
    target_tick: int | None = None
    schema_version: int = COMMAND_SCHEMA_VERSION


class CommandStatus(str, Enum):
    EXECUTED = "executed"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True)
class CommandResult:
    command_id: str
    actor_id: str
    sequence: int
    tick: int
    action_type: str
    status: CommandStatus
    code: str = ""
    message: str = ""

    def to_record(self) -> dict[str, object]:
        return {
            "command_id": self.command_id,
            "actor_id": self.actor_id,
            "sequence": self.sequence,
            "tick": self.tick,
            "action_type": self.action_type,
            "status": self.status.value,
            "code": self.code,
            "message": self.message,
        }
