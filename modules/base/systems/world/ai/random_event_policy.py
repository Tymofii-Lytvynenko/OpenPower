"""Small deterministic response policy for AI-owned random events."""

from __future__ import annotations

import math
from collections.abc import Iterable

from modules.base.systems.world.random_event_policy import EventResponseDefinition


def choose_event_response(
    responses: Iterable[EventResponseDefinition],
    *,
    treasury: float,
    starts_at_minute: int,
    now_minute: int,
    minutes_per_day: int = 1_440,
) -> EventResponseDefinition | None:
    """Choose the most effective affordable option available at this boundary."""
    try:
        balance = float(treasury)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(balance) or balance < 0.0:
        return None

    available = [
        response
        for response in responses
        if response.cost <= balance
        and starts_at_minute + response.available_after_days * minutes_per_day <= now_minute
    ]
    if not available:
        return None
    return min(
        available,
        key=lambda response: (
            -response.mitigation,
            response.risk,
            response.cost,
            response.response_id,
        ),
    )
