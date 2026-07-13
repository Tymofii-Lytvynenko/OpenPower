from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import orjson

from src.shared import actions as action_module
from src.shared.actions import GameAction

SCHEDULE_KEYS = {"day", "tick", "minute", "type", "action_type", "payload"}


def _action_classes() -> dict[str, type[GameAction]]:
    classes: dict[str, type[GameAction]] = {}
    for name in dir(action_module):
        value = getattr(action_module, name)
        if not isinstance(value, type) or value is GameAction:
            continue
        if dataclasses.is_dataclass(value) and issubclass(value, GameAction):
            classes[name] = value
    return classes


ACTION_CLASSES = _action_classes()


def build_action_registry(
    additional_action_types: Iterable[type[GameAction]] = (),
) -> dict[str, type[GameAction]]:
    registry: dict[str, type[GameAction]] = {}
    for short_name, action_type in ACTION_CLASSES.items():
        registry[short_name] = action_type
        registry[f"{action_type.__module__}.{action_type.__qualname__}"] = action_type

    ambiguous_short_names: set[str] = set()
    for action_type in additional_action_types:
        if not dataclasses.is_dataclass(action_type) or not issubclass(action_type, GameAction):
            raise TypeError(f"{action_type!r} is not a dataclass GameAction type.")

        qualified_name = f"{action_type.__module__}.{action_type.__qualname__}"
        registry[qualified_name] = action_type
        short_name = action_type.__name__
        existing = registry.get(short_name)
        if existing is not None and existing is not action_type:
            registry.pop(short_name, None)
            ambiguous_short_names.add(short_name)
        elif short_name not in ambiguous_short_names:
            registry[short_name] = action_type
    return registry


@dataclass(frozen=True)
class ScheduledAction:
    action: GameAction
    day: int | None = None
    tick: int | None = None
    minute: int | None = None


class ActionScript:
    def __init__(self, actions: list[ScheduledAction] | None = None):
        self._actions = actions or []

    @classmethod
    def empty(cls) -> "ActionScript":
        return cls([])

    @classmethod
    def from_path(
        cls,
        path: Path,
        action_types: Iterable[type[GameAction]] = (),
    ) -> "ActionScript":
        raw_records = _load_records(path)
        registry = build_action_registry(action_types)
        return cls([_parse_scheduled_action(record, registry) for record in raw_records])

    def actions_for(self, day: int, tick: int, minute: int) -> list[GameAction]:
        matched: list[GameAction] = []
        for scheduled in self._actions:
            if scheduled.day is not None and scheduled.day != day:
                continue
            if scheduled.tick is not None and scheduled.tick != tick:
                continue
            if scheduled.minute is not None and scheduled.minute != minute:
                continue
            if scheduled.day is None and scheduled.tick is None and scheduled.minute is None and day != 1:
                continue
            matched.append(scheduled.action)
        return matched


def _load_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    if text.startswith("["):
        data = orjson.loads(text)
        if not isinstance(data, list):
            raise ValueError(f"Action script JSON root must be a list: {path}")
        return data

    records = []
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        record = orjson.loads(stripped)
        if not isinstance(record, dict):
            raise ValueError(f"Action script line {index} must contain a JSON object.")
        records.append(record)
    return records


def _parse_scheduled_action(
    record: dict[str, Any],
    action_classes: dict[str, type[GameAction]] | None = None,
) -> ScheduledAction:
    action_type = record.get("type") or record.get("action_type")
    if not action_type:
        raise ValueError(f"Action record is missing 'type': {record}")

    registry = action_classes or ACTION_CLASSES
    action_cls = registry.get(str(action_type))
    if action_cls is None:
        known = ", ".join(sorted(registry))
        raise ValueError(f"Unknown action type '{action_type}'. Known actions: {known}")

    payload = dict(record.get("payload") or {})
    for key, value in record.items():
        if key not in SCHEDULE_KEYS:
            payload[key] = value
    payload.setdefault("player_id", "simulation")

    allowed_fields = {field.name for field in dataclasses.fields(action_cls)}
    unknown_fields = sorted(set(payload) - allowed_fields)
    if unknown_fields:
        raise ValueError(f"Action {action_type} received unknown fields: {unknown_fields}")

    return ScheduledAction(
        action=action_cls(**payload),
        day=_optional_int(record.get("day")),
        tick=_optional_int(record.get("tick")),
        minute=_optional_int(record.get("minute")),
    )


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)