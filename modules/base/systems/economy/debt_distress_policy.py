from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class DebtDistressRequest:
    country_id: str
    requested_status: str
    trigger: str
    arrears: float
    now: int
    reason: str


@dataclass(frozen=True)
class DebtDistressInputs:
    country_id: str
    requested_status: str
    trigger: str
    fallback_arrears: float
    country_arrears: Any
    country_gdp: Any
    default_arrears_minimum: Any
    default_arrears_gdp_ratio: Any
    now: int
    reason: str
    case_count: int
    existing_case: dict[str, Any] | None


@dataclass(frozen=True)
class DebtDistressPlan:
    case: dict[str, Any]
    creates_case: bool
    status: str
    total_arrears: float
    modifiers: dict[str, float]
    previous_status: str
    case_id: str


class DebtDistressPlanner(Protocol):
    def plan(self, inputs: DebtDistressInputs) -> DebtDistressPlan: ...


class DeterministicDebtDistressPlanner:
    def plan(self, inputs: DebtDistressInputs) -> DebtDistressPlan:
        total_arrears = max(
            0.0,
            _finite_number(inputs.country_arrears, inputs.fallback_arrears),
        )
        default_threshold = self._default_threshold(inputs)
        existing_case = inputs.existing_case
        current_status = str((existing_case or {}).get("status") or "")
        status = self._resolve_status(inputs, total_arrears, default_threshold, current_status)
        creates_case = existing_case is None
        case_id = self._case_id(inputs, existing_case)
        restrictions = _restrictions(status)
        case = self._create_or_update_case(
            inputs,
            existing_case,
            case_id,
            status,
            total_arrears,
            restrictions,
        )

        return DebtDistressPlan(
            case=case,
            creates_case=creates_case,
            status=status,
            total_arrears=total_arrears,
            modifiers=restrictions,
            previous_status=current_status,
            case_id=case_id,
        )

    def _default_threshold(self, inputs: DebtDistressInputs) -> float:
        default_floor = _bounded(
            inputs.default_arrears_minimum,
            0.0,
            1_000_000_000_000.0,
            100.0,
        )
        default_share = _bounded(inputs.default_arrears_gdp_ratio, 0.0, 1.0, 0.1)
        return max(
            default_floor,
            _finite_number(inputs.country_gdp) * default_share,
        )

    def _resolve_status(
        self,
        inputs: DebtDistressInputs,
        total_arrears: float,
        default_threshold: float,
        current_status: str,
    ) -> str:
        status = (
            "default"
            if total_arrears >= default_threshold or current_status == "default"
            else inputs.requested_status
        )
        if current_status == "restructuring" and status == "arrears":
            status = "restructuring"
        return status

    def _case_id(
        self,
        inputs: DebtDistressInputs,
        existing_case: dict[str, Any] | None,
    ) -> str:
        if existing_case is not None:
            return str(existing_case["id"])
        return (
            f"distress:{inputs.country_id}:{inputs.now}:{inputs.case_count}"
        )

    def _create_or_update_case(
        self,
        inputs: DebtDistressInputs,
        existing_case: dict[str, Any] | None,
        case_id: str,
        status: str,
        total_arrears: float,
        restrictions: dict[str, float],
    ) -> dict[str, Any]:
        if existing_case is None:
            return {
                "id": case_id,
                "country_id": inputs.country_id,
                "status": status,
                "trigger": inputs.trigger,
                "entered_at_minute": inputs.now,
                "updated_at_minute": inputs.now,
                "arrears_at_entry": total_arrears,
                "restriction_json": json.dumps(restrictions, sort_keys=True),
                "recovery_condition": "All contractual arrears are cleared and treasury is non-negative.",
                "reason": inputs.reason,
            }
        case = dict(existing_case)
        case.update(
            status=status,
            updated_at_minute=inputs.now,
            restriction_json=json.dumps(restrictions, sort_keys=True),
            reason=inputs.reason,
        )
        return case


def _finite_number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _bounded(value: Any, minimum: float, maximum: float, default: float = 0.0) -> float:
    return min(max(_finite_number(value, default), minimum), maximum)


def _restrictions(status: str) -> dict[str, float]:
    configured = {
        "arrears": {
            "production": 0.95, "trade": 0.95, "policy": 0.9,
            "health": 0.98, "politics": 0.98, "creditworthiness": 0.95,
        },
        "restructuring": {
            "production": 0.9, "trade": 0.9, "policy": 0.75,
            "health": 0.95, "politics": 0.9, "creditworthiness": 0.85,
        },
        "default": {
            "production": 0.75, "trade": 0.8, "policy": 0.6,
            "health": 0.9, "politics": 0.75, "creditworthiness": 0.7,
        },
    }
    return configured.get(status, {
        "production": 1.0, "trade": 1.0, "policy": 1.0,
        "health": 1.0, "politics": 1.0, "creditworthiness": 1.0,
    })
