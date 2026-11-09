import polars as pl
import pytest

from modules.base.systems.military import covert_mobilization_signals as signals
from src.shared.events import EventUnitReadinessStarted
from src.shared.state import GameState


def _event(unit_id: str = "unit-1") -> EventUnitReadinessStarted:
    return EventUnitReadinessStarted(
        unit_id=unit_id,
        transition_id="transition-1",
        from_status="parked",
        target_status="ready",
        stage="parked_to_ready",
        started_at_minute=1,
        completes_at_minute=2,
    )


def _normalize(value: object) -> str:
    return str(value or "").strip().upper()


def _context(
    *,
    units: dict[str, dict[str, object]] | None = None,
    countries: dict[str, dict[str, object]] | None = None,
    cells: list[dict[str, object]] | None = None,
) -> signals._SignalContext:
    return signals._SignalContext(
        state=GameState(),
        cells=cells or [],
        countries_by_id=countries or {},
        units_by_id=units or {},
        designs_by_id={},
        now=0,
        normalize_tag=_normalize,
        finite_number=lambda value: float(value or 0.0),
        regional_telecom_capacity=lambda *_args: 0.5,
        country_population=lambda *_args: 1_000.0,
    )


def test_signal_collection_skips_events_without_available_unit_rows() -> None:
    event = _event()
    state_without_units = GameState()
    state_without_id = GameState(tables={"units": pl.DataFrame({"owner": ["AAA"]})})
    state_without_match = GameState(tables={"units": pl.DataFrame({"id": ["other"]})})

    assert signals._signal_rows_for_events(state_without_units, [event]) is None
    assert signals._signal_rows_for_events(state_without_id, [event]) is None
    assert signals._signal_rows_for_events(state_without_match, [event]) is None

    findings: list[dict[str, object]] = []
    state_without_units.events = [event]
    signals.record_mobilization_signals(
        state_without_units,
        [],
        {},
        findings,
        0,
        normalize_tag=_normalize,
        finite_number=lambda value: float(value or 0.0),
        regional_telecom_capacity=lambda *_args: 0.5,
        country_population=lambda *_args: 1_000.0,
    )
    assert findings == []
    assert signals._rows_by_id(
        pl.DataFrame({"owner": ["AAA"]}), {"unit-1"}
    ) == {}


def test_mobilization_observer_must_be_foreign_and_in_the_target_country() -> None:
    same_country = {
        "country_id": "AAA",
        "target_country_id": "AAA",
        "location_country_id": "AAA",
        "assignment": "espionage",
        "status": "active",
    }
    outside_target = {
        **same_country,
        "country_id": "BBB",
        "location_country_id": "BBB",
    }

    assert not signals._is_eligible_observer(same_country, "AAA", _normalize)
    assert not signals._is_eligible_observer(outside_target, "AAA", _normalize)


def test_observation_resolution_handles_missing_units_targets_and_observers() -> None:
    event = _event()
    assert signals._resolve_observation(event, _context()) is None

    unknown_target = _context(units={"unit-1": {"owner": ""}})
    assert signals._resolve_observation(event, unknown_target) is None

    unlisted_observer = _context(
        units={"unit-1": {"owner": "AAA"}},
        countries={"AAA": {"id": "AAA"}},
        cells=[
            {
                "country_id": "BBB",
                "target_country_id": "AAA",
                "location_country_id": "AAA",
                "assignment": "espionage",
                "status": "active",
                "communications_ready": True,
            }
        ],
    )
    assert signals._resolve_observation(event, unlisted_observer) is None


def test_finding_is_not_emitted_when_detection_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(signals, "_resolve_observation", lambda *_args: object())
    monkeypatch.setattr(signals, "_detection_factors", lambda *_args: object())
    monkeypatch.setattr(signals, "_deterministic_seed", lambda *_args: "seed")
    monkeypatch.setattr(signals, "_is_detected", lambda *_args: False)

    assert signals._finding_for_readiness_event(_event(), object(), set()) is None


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"country_id": "BBB"}, False),
        ({"assignment": "espionage"}, False),
        ({"status": "idle"}, False),
        ({"location_country_id": "BBB"}, False),
        ({}, True),
    ],
    ids=["foreign-owner", "wrong-assignment", "inactive", "away-from-home", "active-home-security"],
)
def test_domestic_security_cells_must_be_active_and_at_home(
    changes: dict[str, str],
    expected: bool,
) -> None:
    cell = {
        "country_id": "AAA",
        "assignment": "domestic_security",
        "status": "active",
        "location_country_id": "AAA",
    }
    cell.update(changes)

    assert signals._is_domestic_security_cell(cell, "AAA", _normalize) is expected


@pytest.mark.parametrize(
    ("observer_count", "expected"),
    [(1, "limited"), (2, "sustained"), (4, "dense")],
)
def test_coverage_labels_reflect_observer_count(observer_count: int, expected: str) -> None:
    assert signals._coverage_label(observer_count) == expected
