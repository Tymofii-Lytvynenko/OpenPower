import polars as pl
import pytest

from modules.energy_crisis.actions import ActionSetEnergyPolicy
from modules.energy_crisis.systems.energy_crisis_system import EnergyCrisisSystem
from src.shared.state import GameState


def _action(
    *,
    country_tag: str = "UKR",
    policy: str = "conservation",
    response_level: float = 0.5,
) -> ActionSetEnergyPolicy:
    return ActionSetEnergyPolicy(
        player_id="test",
        country_tag=country_tag,
        policy=policy,
        response_level=response_level,
    )


def test_update_returns_without_crisis_table_and_skips_unrelated_actions() -> None:
    system = EnergyCrisisSystem()
    system.update(GameState(), 1.0)

    state = GameState(tables={"energy_crises": pl.DataFrame()})
    state.current_actions = [object()]
    system.update(state, 1.0)


def test_update_rejects_policy_actions_for_unknown_countries() -> None:
    state = GameState(
        tables={
            "countries": pl.DataFrame({"id": ["UKR"]}),
            "energy_crises": pl.DataFrame({"country_id": ["UKR"]}),
        }
    )
    state.current_actions = [_action(country_tag="XXX")]

    with pytest.raises(ValueError, match="Unknown energy-policy country 'XXX'"):
        EnergyCrisisSystem().update(state, 1.0)


@pytest.mark.parametrize(
    ("policy", "response_level", "message"),
    [
        ("unsupported", 0.5, "Unknown energy policy"),
        ("conservation", float("nan"), "response_level must be finite"),
        ("conservation", 1.1, "response_level must be finite"),
    ],
)
def test_apply_policy_rejects_unknown_policies_and_invalid_responses(
    policy: str,
    response_level: float,
    message: str,
) -> None:
    status = pl.DataFrame({"country_id": ["UKR"]})

    with pytest.raises(ValueError, match=message):
        EnergyCrisisSystem()._apply_policy(
            status,
            "UKR",
            _action(policy=policy, response_level=response_level),
        )


def test_apply_policy_adds_a_default_row_for_a_new_country() -> None:
    empty_status = pl.DataFrame(
        {"country_id": pl.Series([], dtype=pl.String)}
    )

    updated = EnergyCrisisSystem()._apply_policy(
        empty_status,
        "UKR",
        _action(policy="rationing", response_level=0.8),
    )

    assert updated.to_dicts() == [
        {
            "country_id": "UKR",
            "policy": "rationing",
            "reserve_days": 90.0,
            "import_dependency": 0.5,
            "shock_intensity": 0.0,
            "response_level": 0.8,
            "stress_index": 0.0,
            "economic_drag": 0.0,
        }
    ]


def test_country_helpers_handle_missing_schema_and_non_numeric_ratios() -> None:
    system = EnergyCrisisSystem()
    no_countries = GameState()
    malformed_countries = GameState(
        tables={"countries": pl.DataFrame({"tag": ["UKR"]})}
    )

    assert system._country_tags(no_countries) == set()
    assert system._country_tags(malformed_countries) == set()
    system._update_country_metrics(no_countries, pl.DataFrame())
    assert system._ratio(None, default=0.25) == 0.25
    assert system._ratio("not-a-number", default=0.25) == 0.25
    assert system._ratio(float("inf"), default=0.25) == 0.25
