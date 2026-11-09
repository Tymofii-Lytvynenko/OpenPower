from __future__ import annotations

import json
from types import SimpleNamespace

import polars as pl

import modules.base.systems.politics.politics_system as politics_module
from modules.base.systems.politics.politics_system import PoliticsSystem
from src.shared.state import GameState


def _crisis_rules() -> pl.DataFrame:
    active_rule = {
        "id": "approval-protest",
        "type": "protest",
        "metric": "approval",
        "threshold": 40.0,
        "direction": "below",
        "recovery_threshold": 50.0,
        "priority": 1,
    }
    return pl.DataFrame(
        {
            "government_form_id": ["known", "empty"],
            "crisis_rules_json": [json.dumps([active_rule]), "[]"],
        }
    )


def _threshold_state(
    *,
    countries: pl.DataFrame | None = None,
    governments: pl.DataFrame | None = None,
) -> GameState:
    return GameState(
        tables={
            "countries": pl.DataFrame({"id": ["USA"]}) if countries is None else countries,
            "country_governments": pl.DataFrame() if governments is None else governments,
            "government_form_rules": _crisis_rules(),
            "political_crises": pl.DataFrame(),
            "political_effects": pl.DataFrame(),
            "political_history": pl.DataFrame(),
            "messages": pl.DataFrame(),
            "news_items": pl.DataFrame(),
        }
    )


def test_one_time_effects_mark_unresolvable_targets_as_skipped():
    state = GameState(
        tables={
            "countries": pl.DataFrame({"id": ["USA"], "gvt_approval": [60.0]}),
            "political_effects": pl.DataFrame(
                [
                    {
                        "id": "effect-1",
                        "country_id": "CAN",
                        "source_type": "political_crisis",
                        "effect": "approval_delta",
                        "value": -5.0,
                        "effective_at_minute": 0,
                        "status": "pending",
                    }
                ]
            ),
        }
    )

    PoliticsSystem()._apply_one_time_political_effects(state)

    assert state.get_table("political_effects")["status"].to_list() == ["skipped"]


def test_crisis_evaluation_returns_when_required_tables_or_country_rows_are_missing():
    system = PoliticsSystem()
    system._evaluate_crisis_thresholds(GameState())

    empty_countries = _threshold_state(
        countries=pl.DataFrame(schema={"id": pl.Utf8})
    )
    system._evaluate_crisis_thresholds(empty_countries)

    missing_id = _threshold_state(countries=pl.DataFrame({"country_tag": ["USA"]}))
    system._evaluate_crisis_thresholds(missing_id)


def test_crisis_evaluation_skips_missing_governments_and_empty_rule_sets():
    system = PoliticsSystem()
    without_government = _threshold_state()
    system._evaluate_crisis_thresholds(without_government)

    without_rules = _threshold_state(
        governments=pl.DataFrame(
            {"country_id": ["USA"], "government_form_id": ["empty"]}
        )
    )
    system._evaluate_crisis_thresholds(without_rules)


def test_stale_recovery_transition_without_an_active_crisis_is_ignored(monkeypatch):
    monkeypatch.setattr(
        politics_module,
        "evaluate_crisis_transitions",
        lambda *_args: [
            SimpleNamespace(
                status="resolved",
                rule=SimpleNamespace(rule_id="missing-crisis"),
                reason="recovery threshold reached",
            )
        ],
    )
    state = _threshold_state(
        governments=pl.DataFrame(
            {"country_id": ["USA"], "government_form_id": ["known"]}
        )
    )

    PoliticsSystem()._evaluate_crisis_thresholds(state)

    assert state.get_table("political_crises").is_empty()


def test_finite_values_use_defaults_for_invalid_and_non_finite_inputs():
    system = PoliticsSystem()

    assert system._finite("not-a-number", 7.0) == 7.0
    assert system._finite(float("inf"), 7.0) == 7.0
