from __future__ import annotations

import hashlib
from typing import Any

from src.shared.state import GameState, persistent_state_fields
from src.simulation.serialization import dumps_line, to_plain_data


def state_fingerprint(state: GameState) -> str:
    """Return a canonical hash of every persistent simulation field."""

    digest = hashlib.sha256()
    for state_field in persistent_state_fields():
        _update_chunk(digest, state_field.name.encode("utf-8"))
        value = getattr(state, state_field.name)
        if state_field.name == "tables":
            _update_tables(digest, value)
        else:
            _update_chunk(digest, dumps_line(to_plain_data(value)))
    return digest.hexdigest()


def _update_tables(digest: Any, tables: dict[str, Any]) -> None:
    for table_name, frame in sorted(tables.items()):
        _update_chunk(digest, table_name.encode("utf-8"))
        schema = [(column, str(dtype)) for column, dtype in frame.schema.items()]
        _update_chunk(digest, dumps_line(schema))
        for row in frame.iter_rows(named=True):
            _update_chunk(digest, dumps_line(row))


def _update_chunk(digest: Any, payload: bytes) -> None:
    digest.update(len(payload).to_bytes(8, byteorder="big", signed=False))
    digest.update(payload)
