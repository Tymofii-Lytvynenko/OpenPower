from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.shared.events import EventEconomicTransition


@dataclass(frozen=True)
class EconomicTransitionEventRequest:
    event_type: str
    country_id: str
    source_id: str
    indicator: str
    previous_value: float
    new_value: float
    reason: str
    at_minute: int

    def to_event(self) -> EventEconomicTransition:
        return EventEconomicTransition(
            event_type=self.event_type,
            country_id=self.country_id,
            source_id=self.source_id,
            indicator=self.indicator,
            previous_value=float(self.previous_value),
            new_value=float(self.new_value),
            reason=self.reason,
            at_minute=self.at_minute,
        )


@dataclass(frozen=True)
class EconomicRejectionRequest:
    country_id: str
    source_id: str
    indicator: str
    value: float
    reason: str
    at_minute: int

    def to_event_request(self) -> EconomicTransitionEventRequest:
        return EconomicTransitionEventRequest(
            event_type="rejected",
            country_id=self.country_id,
            source_id=self.source_id,
            indicator=self.indicator,
            previous_value=self.value,
            new_value=self.value,
            reason=self.reason,
            at_minute=self.at_minute,
        )


@dataclass(frozen=True)
class EconomicCauseRecordRequest:
    country_id: str
    source_type: str
    source_id: str
    indicator: str
    previous_value: float
    new_value: float
    unit: str
    game_minute: int
    reason: str

    def to_record(self) -> dict[str, Any] | None:
        previous_value = float(self.previous_value)
        new_value = float(self.new_value)
        if abs(new_value - previous_value) < 1e-9:
            return None

        return {
            "id": f"{self.source_id}:{self.country_id}:{self.indicator}",
            "country_id": self.country_id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "indicator": self.indicator,
            "previous_value": previous_value,
            "new_value": new_value,
            "delta": new_value - previous_value,
            "unit": self.unit,
            "game_minute": int(self.game_minute),
            "reason": self.reason,
            "confidence": 1.0,
            "completeness": "complete",
        }
