from __future__ import annotations

import copy
import dataclasses
import io
from dataclasses import dataclass
from typing import Any

import polars as pl

from src.shared.determinism import DeterminismState
from src.shared.events import JournalState
from src.shared.state import GameState, TimeData


SNAPSHOT_PROTOCOL_VERSION = 2


class SnapshotProtocolError(RuntimeError):
    pass


@dataclass(frozen=True)
class _SnapshotDescriptor:
    table_revisions: dict[str, int]
    table_names: frozenset[str]
    domain_event_count: int
    command_result_count: int


def _serialize_frame(frame: pl.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.write_ipc(buffer)
    return buffer.getvalue()


def _deserialize_frame(payload: bytes) -> pl.DataFrame:
    return pl.read_ipc(io.BytesIO(payload))


class StateSnapshotEncoder:
    """Produces acknowledged table deltas instead of resending the full world."""

    def __init__(self):
        self.sequence = 0
        self.base_sequence = 0
        self._base: _SnapshotDescriptor | None = None
        self._sent: dict[int, _SnapshotDescriptor] = {}

    def acknowledge(self, sequence: int) -> None:
        descriptor = self._sent.get(int(sequence))
        if descriptor is None or sequence < self.base_sequence:
            return
        self.base_sequence = int(sequence)
        self._base = descriptor
        self._sent = {
            sent_sequence: sent_descriptor
            for sent_sequence, sent_descriptor in self._sent.items()
            if sent_sequence >= self.base_sequence
        }

    def encode(self, state: GameState, force_full: bool = False) -> dict[str, Any]:
        self.sequence += 1
        descriptor = _SnapshotDescriptor(
            table_revisions=dict(state.table_revisions),
            table_names=frozenset(state.tables),
            domain_event_count=len(state.journal.domain_events),
            command_result_count=len(state.journal.command_results),
        )
        is_full = force_full or self._base is None
        if is_full:
            table_names = sorted(state.tables)
            removed_tables: list[str] = []
            base_sequence = 0
        else:
            assert self._base is not None
            table_names = sorted(
                name
                for name in state.tables
                if state.table_revisions.get(name, 0)
                != self._base.table_revisions.get(name, 0)
            )
            removed_tables = sorted(self._base.table_names - state.tables.keys())
            base_sequence = self.base_sequence

        packet: dict[str, Any] = {
            "protocol_version": SNAPSHOT_PROTOCOL_VERSION,
            "kind": "full" if is_full else "delta",
            "sequence": self.sequence,
            "base_sequence": base_sequence,
            "tables": {
                name: _serialize_frame(state.tables[name])
                for name in table_names
            },
            "removed_tables": removed_tables,
            "table_revisions": dict(state.table_revisions),
            "time": dataclasses.asdict(state.time),
            "globals": copy.deepcopy(state.globals),
            "system_state": copy.deepcopy(state.system_state),
            "determinism": dataclasses.asdict(state.determinism),
            "events": copy.deepcopy(state.events),
        }
        if is_full:
            packet["journal"] = dataclasses.asdict(state.journal)
            self.base_sequence = self.sequence
            self._base = descriptor
        else:
            assert self._base is not None
            packet["domain_events"] = copy.deepcopy(
                state.journal.domain_events[self._base.domain_event_count :]
            )
            packet["command_results"] = copy.deepcopy(
                state.journal.command_results[self._base.command_result_count :]
            )

        self._sent[self.sequence] = descriptor
        if len(self._sent) > 256:
            keep = {self.base_sequence, *sorted(self._sent)[-255:]}
            self._sent = {
                sequence: item
                for sequence, item in self._sent.items()
                if sequence in keep
            }
        return packet


class StateSnapshotDecoder:
    def __init__(self):
        self.state: GameState | None = None
        self.sequence = 0

    def decode(self, packet: dict[str, Any]) -> GameState:
        version = int(packet.get("protocol_version", 0))
        if version != SNAPSHOT_PROTOCOL_VERSION:
            raise SnapshotProtocolError(
                f"Unsupported snapshot protocol {version}; expected {SNAPSHOT_PROTOCOL_VERSION}."
            )

        kind = packet.get("kind")
        if kind == "full":
            state = GameState(
                tables={
                    name: _deserialize_frame(payload)
                    for name, payload in packet["tables"].items()
                },
                time=TimeData(**packet["time"]),
                globals=copy.deepcopy(packet["globals"]),
                system_state=copy.deepcopy(packet.get("system_state", {})),
                determinism=DeterminismState(**packet.get("determinism", {})),
                journal=JournalState(**packet.get("journal", {})),
                events=copy.deepcopy(packet.get("events", [])),
            )
            self.state = state
        elif kind == "delta":
            if self.state is None:
                raise SnapshotProtocolError("Received a delta before a full snapshot.")
            base_sequence = int(packet.get("base_sequence", 0))
            if base_sequence > self.sequence:
                raise SnapshotProtocolError(
                    f"Snapshot delta requires sequence {base_sequence}, "
                    f"client has {self.sequence}."
                )
            state = self.state
            for name, payload in packet["tables"].items():
                state.tables[name] = _deserialize_frame(payload)
            for name in packet.get("removed_tables", []):
                state.tables.pop(name, None)
            state.time = TimeData(**packet["time"])
            state.globals = copy.deepcopy(packet["globals"])
            state.system_state = copy.deepcopy(packet.get("system_state", {}))
            state.determinism = DeterminismState(**packet.get("determinism", {}))
            state.events = copy.deepcopy(packet.get("events", []))
            self._merge_journal(
                state.journal.domain_events,
                packet.get("domain_events", []),
                "event_id",
            )
            self._merge_journal(
                state.journal.command_results,
                packet.get("command_results", []),
                "command_id",
            )
        else:
            raise SnapshotProtocolError(f"Unknown snapshot kind '{kind}'.")

        assert self.state is not None
        self.state._table_revisions = dict(packet.get("table_revisions", {}))
        self.sequence = int(packet["sequence"])
        return self.state

    @staticmethod
    def _merge_journal(
        target: list[dict[str, Any]],
        incoming: list[dict[str, Any]],
        identifier: str,
    ) -> None:
        known = {str(record.get(identifier, "")) for record in target}
        for record in incoming:
            record_id = str(record.get(identifier, ""))
            if record_id and record_id in known:
                continue
            target.append(copy.deepcopy(record))
            if record_id:
                known.add(record_id)
