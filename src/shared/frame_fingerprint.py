"""Deterministic fingerprints for small read-model projections."""
from __future__ import annotations

from hashlib import blake2b
from io import BytesIO

import polars as pl


def frame_fingerprint(frame: pl.DataFrame, columns: list[str]) -> str:
    buffer = BytesIO()
    frame.select(columns).rechunk().write_ipc(buffer)
    return blake2b(buffer.getbuffer(), digest_size=16).hexdigest()
