import json

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.world.infrastructure_system import InfrastructureSystem
from modules.base.systems.world.random_event_policy import EVENT_BY_TYPE
from modules.base.systems.world.random_events_system import RandomEventsSystem
from src.shared.actions import ActionRespondToRandomEvent
from src.shared.determinism import DeterminismState
from src.shared.events import EventNewDay, EventRandomEventTriggered
from tests.test_regional_infrastructure_fixtures import build_infrastructure_state


def test_disaster_effects_are_bounded_and_apply_once_through_infrastructure() -> None:
    state = build_infrastructure_state()
    ensure_base_tables(state)
    state.determinism = DeterminismState(seed=7)
    state.time.total_minutes = 1_440
    state.globals["random_event_daily_chance"] = 1.0
    infrastructure = InfrastructureSystem()
    infrastructure.update(state, 0.0)
    events = RandomEventsSystem()
    events.update(state, 0.0)
    state.globals["random_event_frequency_multiplier"] = 4.0
    state.update_table(
        "random_event_controls",
        state.tables["random_event_controls"].with_columns(
            (pl.col("category") == "disaster").alias("enabled")
        ),
    )

    state.events = [EventNewDay(state.time.day, state.time.month, state.time.year)]
    events.update(state, 0.0)
    trigger = next(event for event in state.events if isinstance(event, EventRandomEventTriggered))
    definition = EVENT_BY_TYPE[trigger.event_type]
    expected_categories = {
        effect.category.removeprefix("infrastructure_")
        for effect in definition.effects
        if effect.category.startswith("infrastructure_")
    }
    effects = state.tables["random_event_effects"].filter(
        (pl.col("event_id") == trigger.event_id)
        & pl.col("category").is_in(
            [f"infrastructure_{category}" for category in expected_categories]
        )
    )
    assert expected_categories
    assert effects.height == len(expected_categories)
    assert effects["magnitude"].is_between(0.0, 1.0, closed="both").all()

    infrastructure.update(state, 0.0)
    first_damage = state.tables["infrastructure_damage_records"].filter(
        pl.col("source_id") == trigger.event_id
    )
    assert {row["category"] for row in first_damage.iter_rows(named=True)} == expected_categories
    for effect in effects.iter_rows(named=True):
        category = effect["category"].removeprefix("infrastructure_")
        damage = first_damage.filter(pl.col("category") == category).row(0, named=True)
        assert damage["severity"] == effect["magnitude"]

    state.events = [trigger]
    infrastructure.update(state, 0.0)
    second_damage = state.tables["infrastructure_damage_records"].filter(
        pl.col("source_id") == trigger.event_id
    )
    assert second_damage.height == first_damage.height


def test_accepted_disaster_response_reduces_existing_infrastructure_damage() -> None:
    state = build_infrastructure_state()
    ensure_base_tables(state)
    state.determinism = DeterminismState(seed=17)
    state.globals["player_country_map"] = {"player-usa": "USA", "player-can": "CAN"}
    state.time.total_minutes = 1_440
    state.globals["random_event_daily_chance"] = 1.0
    infrastructure = InfrastructureSystem()
    infrastructure.update(state, 0.0)
    events = RandomEventsSystem()
    events.update(state, 0.0)
    state.globals["random_event_frequency_multiplier"] = 4.0
    state.update_table(
        "random_event_controls",
        state.tables["random_event_controls"].with_columns(
            (pl.col("category") == "disaster").alias("enabled")
        ),
    )
    state.events = [EventNewDay(state.time.day, state.time.month, state.time.year)]
    events.update(state, 0.0)
    instance = state.tables["random_event_instances"].row(0, named=True)
    effect = state.tables["random_event_effects"].filter(
        (pl.col("event_id") == instance["id"])
        & pl.col("category").is_in(
            [
                "infrastructure_transport",
                "infrastructure_utilities",
                "infrastructure_industrial",
                "infrastructure_telecom",
            ]
        )
    ).row(0, named=True)
    infrastructure_category = effect["category"].removeprefix("infrastructure_")
    infrastructure.update(state, 0.0)
    damage_before = state.tables["infrastructure_damage_records"].filter(
        pl.col("id")
        == f"disaster:{instance['id']}:{effect['subject_id']}:{infrastructure_category}"
    ).row(0, named=True)
    profile_before = state.tables["regional_infrastructure"].filter(
        (pl.col("region_id") == int(effect["subject_id"]))
        & (pl.col("category") == infrastructure_category)
    ).row(0, named=True)

    player_id = "player-usa" if instance["country_id"] == "USA" else "player-can"
    response_id = json.loads(instance["response_options_json"])[0]["response_id"]
    state.current_actions = [
        ActionRespondToRandomEvent(
            player_id=player_id,
            event_id=instance["id"],
            response_id=response_id,
            country_tag=instance["country_id"],
        )
    ]
    state.events = []
    events.update(state, 0.0)
    infrastructure.update(state, 0.0)

    damage_after = state.tables["infrastructure_damage_records"].filter(
        pl.col("id") == damage_before["id"]
    ).row(0, named=True)
    profile_after = state.tables["regional_infrastructure"].filter(
        (pl.col("region_id") == int(effect["subject_id"]))
        & (pl.col("category") == infrastructure_category)
    ).row(0, named=True)
    effect_after = state.tables["random_event_effects"].filter(
        pl.col("id") == effect["id"]
    ).row(0, named=True)
    assert damage_after["severity"] < damage_before["severity"]
    assert profile_after["condition"] > profile_before["condition"]
    assert effect_after["mitigation_pending"] is False


def test_stacked_infrastructure_effects_keep_category_values_bounded() -> None:
    state = build_infrastructure_state()
    ensure_base_tables(state)
    state.determinism = DeterminismState(seed=7)
    state.time.total_minutes = 1_440
    state.globals["random_event_daily_chance"] = 1.0
    infrastructure = InfrastructureSystem()
    infrastructure.update(state, 0.0)
    events = RandomEventsSystem()
    events.update(state, 0.0)
    state.globals["random_event_frequency_multiplier"] = 4.0
    state.update_table(
        "random_event_controls",
        state.tables["random_event_controls"].with_columns(
            (pl.col("category") == "disaster").alias("enabled")
        ),
    )
    state.events = [EventNewDay(state.time.day, state.time.month, state.time.year)]
    events.update(state, 0.0)
    trigger = next(event for event in state.events if isinstance(event, EventRandomEventTriggered))
    first_effect = state.tables["random_event_effects"].filter(
        (pl.col("event_id") == trigger.event_id)
        & pl.col("category").is_in(
            [
                "infrastructure_transport",
                "infrastructure_utilities",
                "infrastructure_industrial",
                "infrastructure_telecom",
            ]
        )
    ).row(0, named=True)
    category = first_effect["category"].removeprefix("infrastructure_")
    region_id = int(first_effect["subject_id"])
    infrastructure.update(state, 0.0)
    region_profile = state.tables["regional_infrastructure"].filter(
        (pl.col("region_id") == region_id) & (pl.col("category") == category)
    ).row(0, named=True)

    existing_effects = state.tables["random_event_effects"]
    stacked_effect = {
        "id": f"stacked-event:region:{region_id}:infrastructure",
        "event_id": "stacked-event",
        "category": first_effect["category"],
        "subject_type": "region",
        "subject_id": str(region_id),
        "magnitude": 0.95,
        "unit": "ratio",
        "application_mode": "immediate",
        "starts_at_minute": state.time.total_minutes,
        "expires_at_minute": state.time.total_minutes + 1_440,
        "last_applied_at_minute": 0,
        "status": "pending",
        "mitigation_pending": False,
        "recovery_state_json": "{}",
    }
    addition = pl.DataFrame([stacked_effect], schema=existing_effects.schema)
    state.update_table(
        "random_event_effects",
        pl.concat([existing_effects, addition], how="vertical"),
    )
    state.events = []
    infrastructure.update(state, 0.0)

    stacked_profile = state.tables["regional_infrastructure"].filter(
        (pl.col("region_id") == region_id) & (pl.col("category") == category)
    ).row(0, named=True)
    assert 0.0 <= stacked_profile["condition"] <= 1.0
    assert 0.0 <= stacked_profile["capacity"] <= stacked_profile["level"] <= 1.0
    assert state.tables["infrastructure_damage_records"].filter(
        (pl.col("region_id") == region_id) & (pl.col("category") == category)
    ).height >= 2
