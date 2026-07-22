from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable

from src.shared.commands import (
    COMMAND_SCHEMA_VERSION,
    CommandEnvelope,
    CommandResult,
    CommandStatus,
)
from src.shared.state import GameState


CommandValidator = Callable[[CommandEnvelope, GameState], str | None]


@dataclass(frozen=True)
class PreparedCommands:
    ready: tuple[CommandEnvelope, ...]
    rejected: tuple[CommandResult, ...]


class CommandPipeline:
    """Validates, sequences, and schedules authoritative external commands."""

    def __init__(
        self,
        validators: Iterable[CommandValidator] = (),
        initial_sequences: dict[str, int] | None = None,
    ):
        self._validators = tuple(validators)
        self._pending: list[CommandEnvelope] = []
        self._seen_ids: set[str] = set()
        self._last_sequence: dict[str, int] = defaultdict(int)
        if initial_sequences:
            self._last_sequence.update(
                {actor: max(0, int(sequence)) for actor, sequence in initial_sequences.items()}
            )

    def submit(self, command: CommandEnvelope) -> None:
        self._pending.append(command)

    def prepare(self, state: GameState, tick: int) -> PreparedCommands:
        ready: list[CommandEnvelope] = []
        deferred: list[CommandEnvelope] = []
        rejected: list[CommandResult] = []
        blocked_actors: set[str] = set()

        for command in self._pending:
            if command.actor_id in blocked_actors:
                deferred.append(command)
                continue
            if command.target_tick is not None and command.target_tick > tick:
                deferred.append(command)
                blocked_actors.add(command.actor_id)
                continue

            protocol_error = self._protocol_error(command)
            if protocol_error is not None:
                rejected.append(
                    self.result(
                        command,
                        tick,
                        CommandStatus.REJECTED,
                        "protocol_error",
                        protocol_error,
                    )
                )
                self._seen_ids.add(command.command_id)
                continue

            validation_error = next(
                (
                    error
                    for validator in self._validators
                    if (error := validator(command, state))
                ),
                None,
            )
            self._seen_ids.add(command.command_id)
            self._last_sequence[command.actor_id] = command.sequence
            if validation_error is not None:
                rejected.append(
                    self.result(
                        command,
                        tick,
                        CommandStatus.REJECTED,
                        "validation_error",
                        validation_error,
                    )
                )
                continue

            ready.append(command)

        self._pending = deferred
        return PreparedCommands(tuple(ready), tuple(rejected))

    def result(
        self,
        command: CommandEnvelope,
        tick: int,
        status: CommandStatus,
        code: str = "",
        message: str = "",
    ) -> CommandResult:
        return CommandResult(
            command_id=command.command_id,
            actor_id=command.actor_id,
            sequence=command.sequence,
            tick=int(tick),
            action_type=type(command.action).__name__,
            status=status,
            code=code,
            message=message,
        )

    def _protocol_error(self, command: CommandEnvelope) -> str | None:
        if command.schema_version != COMMAND_SCHEMA_VERSION:
            return (
                f"Unsupported command schema {command.schema_version}; "
                f"expected {COMMAND_SCHEMA_VERSION}."
            )
        if not command.command_id:
            return "Command id cannot be empty."
        if command.command_id in self._seen_ids:
            return f"Duplicate command id '{command.command_id}'."
        if not command.actor_id:
            return "Actor id cannot be empty."
        if command.action.player_id != command.actor_id:
            return "Command actor does not match action player_id."
        expected_sequence = self._last_sequence[command.actor_id] + 1
        if command.sequence != expected_sequence:
            return (
                f"Out-of-order sequence {command.sequence} for '{command.actor_id}'; "
                f"expected {expected_sequence}."
            )
        return None
