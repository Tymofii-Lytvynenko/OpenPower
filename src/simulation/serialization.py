from __future__ import annotations

import dataclasses
import math
from pathlib import Path
from typing import Any

import orjson

JSON_OPTIONS = orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS | orjson.OPT_SERIALIZE_NUMPY
JSON_LINE_OPTIONS = orjson.OPT_SORT_KEYS | orjson.OPT_SERIALIZE_NUMPY


def to_plain_data(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {field.name: to_plain_data(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_plain_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_plain_data(item) for item in value]
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def dumps_pretty(data: Any) -> bytes:
    return orjson.dumps(to_plain_data(data), option=JSON_OPTIONS)


def dumps_line(data: Any) -> bytes:
    return orjson.dumps(to_plain_data(data), option=JSON_LINE_OPTIONS)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dumps_pretty(data))