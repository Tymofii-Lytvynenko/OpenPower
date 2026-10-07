"""Shared research prerequisite checks for designs and production orders."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def research_requirements_met(
    requirements_value: Any,
    research_levels: Mapping[str, Any],
) -> bool:
    """Check persisted design requirements using the same normalization as actions."""
    requirements: Any = requirements_value
    if isinstance(requirements_value, str):
        try:
            requirements = json.loads(requirements_value or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            requirements = {}
    if not isinstance(requirements, dict):
        return False

    normalized_levels = {
        str(branch or "").strip().lower(): _nonnegative_int(level)
        for branch, level in research_levels.items()
    }
    return all(
        normalized_levels.get(str(branch or "").strip().lower(), 0)
        >= _nonnegative_int(level)
        for branch, level in requirements.items()
    )


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError, OverflowError):
        return 0
