from __future__ import annotations

import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from modules.base.systems.politics.foreign_constitutional_policy import (
    _integer,
    _tags,
    build_foreign_government_effects,
)
from modules.base.systems.politics.political_lifecycle_system import PoliticalLifecycleSystem
from src.shared.actions import ActionSetGovernmentForm
from src.shared.events import (
    EventGovernmentFormChanged,
    EventMartialLawChanged,
    EventTreatyLifecycleChanged,
)
from src.shared.state import GameState
from src.shared.treaties import TREATY_EFFECT_SCHEMA, TREATY_SCHEMA


def _world(eligible_parties: int = 1) -> tuple[GameState, PoliticalLifecycleSystem]:
    parties = [
        {
            "country_id": "AAA",
            "party_id": f"party-{index}",
            "eligible": True,
            "is_ruling": index == 0,
            "display_name": f"Party {index}",
            "support_share": 1.0 if index == 0 else 0.0,
        }
        for index in range(eligible_parties)
    ]
    state = GameState(
        tables={
            "countries": pl.DataFrame([{"id": "AAA", "money_reserves": 100.0}]),
            "country_governments": pl.DataFrame(
                [
                    {
                        "country_id": "AAA",
                        "government_type": "Custom republic",
                        "government_form_id": "custom republic",
                        "ruling_party_id": "party-0",
                        "capital_region_id": 1,
                        "initialized": True,
                        "election_eligible": True,
                        "next_election_at_minute": 20_000,
                        "martial_law": True,
                        "crisis_status": "none",
                    }
                ]
            ),
            "government_form_rules": pl.DataFrame(
                [
                    {
                        "government_form_id": "custom republic",
                        "display_name": "Custom republic",
                        "election_eligible": True,
                        "election_interval_minutes": 10_000,
                        "minimum_eligible_parties": 1,
                        "maximum_eligible_parties": 0,
                    },
                    {
                        "government_form_id": "single-party democracy",
                        "display_name": "Single-party democracy",
                        "election_eligible": True,
                        "election_interval_minutes": 8_000,
                        "minimum_eligible_parties": 1,
                        "maximum_eligible_parties": 1,
                    },
                    {
                        "government_form_id": "multi-party democracy",
                        "display_name": "Multi-party democracy",
                        "election_eligible": True,
                        "election_interval_minutes": 8_000,
                        "minimum_eligible_parties": 2,
                        "maximum_eligible_parties": 0,
                    },
                ]
            ),
            "political_parties": pl.DataFrame(parties),
        },
        globals={"player_country_map": {"player": "AAA"}},
    )
    ensure_base_tables(state)
    system = PoliticalLifecycleSystem()
    system.update(state, 0.0)
    state.events.clear()
    state.journal.command_results.clear()
    return state, system


def test_military_override_target_uses_the_authoritative_form_transition() -> None:
    state, system = _world()
    state.update_table(
        "country_governments",
        state.tables["country_governments"].with_columns(
            pl.lit(False).alias("martial_law")
        ),
    )
    state.current_actions = [
        ActionSetGovernmentForm(
            "player", "AAA", "custom republic", "military-led state"
        )
    ]

    system.update(state, 0.0)

    government = state.tables["country_governments"].row(0, named=True)
    assert government["government_form_id"] == "military-led state"
    assert government["government_type"] == "Military-led state"
    assert government["election_eligible"] is False
    assert government["next_election_at_minute"] == 0
    assert state.journal.command_results[-1]["status"] == "applied"
    event = next(
        event for event in state.events if isinstance(event, EventGovernmentFormChanged)
    )
    assert (event.previous_form_id, event.new_form_id) == (
        "custom republic",
        "military-led state",
    )


def test_direct_form_change_updates_elections_history_and_clears_martial_law() -> None:
    state, system = _world()
    state.update_table(
        "law_transitions",
        pl.DataFrame(
            [
                {
                    "id": "cancel-on-regime-change",
                    "country_id": "AAA",
                    "status": "scheduled",
                    "carry_over_rule": "cancel_on_regime_change",
                    "effective_at_minute": 50_000,
                },
                {
                    "id": "carry-over",
                    "country_id": "AAA",
                    "status": "scheduled",
                    "carry_over_rule": "carry_over",
                    "effective_at_minute": 50_000,
                },
            ],
            schema=state.tables["law_transitions"].schema,
            strict=False,
        ),
    )
    state.update_table(
        "political_elections",
        pl.DataFrame(
            [
                {
                    "id": "old-election",
                    "country_id": "AAA",
                    "government_form_id": "custom republic",
                    "status": "scheduled",
                    "scheduled_at_minute": 20_000,
                }
            ],
            schema=state.tables["political_elections"].schema,
            strict=False,
        ),
    )
    state.current_actions = [
        ActionSetGovernmentForm("player", "AAA", "custom republic", "single-party democracy")
    ]

    system.update(state, 0.0)

    government = state.tables["country_governments"].row(0, named=True)
    assert government["government_form_id"] == "single-party democracy"
    assert government["government_type"] == "Single-party democracy"
    assert government["next_election_at_minute"] == 8_000
    assert government["martial_law"] is False
    assert state.tables["law_transitions"].filter(pl.col("id") == "cancel-on-regime-change").item(0, "status") == "cancelled"
    assert state.tables["law_transitions"].filter(pl.col("id") == "carry-over").item(0, "status") == "scheduled"
    assert state.tables["political_elections"].filter(pl.col("id") == "old-election").item(0, "status") == "cancelled"
    assert state.tables["political_elections"].filter(pl.col("status") == "scheduled").item(0, "scheduled_at_minute") == 8_000
    direct_changes = state.tables["political_history"].filter(
        pl.col("source_type") == "direct_constitutional_change"
    )
    assert direct_changes.height == 2
    assert set(direct_changes["event_type"].to_list()) == {
        "government_form_changed",
        "martial_law_changed",
    }
    assert state.journal.command_results[-1]["status"] == "applied"


def test_confirmed_75_percent_foreign_form_change_releases_regions_and_grants_access() -> None:
    state, system = _foreign_world(controlled_regions=3, at_war=False)
    state.current_actions = [
        ActionSetGovernmentForm(
            "player",
            "POL",
            "custom republic",
            "single-party democracy",
            expected_martial_law=False,
            target_martial_law=False,
            confirmed_foreign_change=True,
        )
    ]

    system.update(state, 0.0)

    government = state.tables["country_governments"].filter(
        pl.col("country_id") == "POL"
    ).row(0, named=True)
    assert government["government_form_id"] == "single-party democracy"
    assert state.journal.command_results[-1]["status"] == "applied"
    assert state.tables["countries_relations"].get_column("value").to_list() == [100.0, 100.0]
    assert state.tables["regions"]["controller"].to_list() == ["POL"] * 4
    access = state.tables["countries_treaties"].filter(
        pl.col("type") == "military_trespassing_right"
    )
    assert access.height == 1
    assert set(access.row(0, named=True)["members"]) == {"AAA", "POL"}
    assert set(state.tables["treaty_effects"]["effect"].to_list()) == {"transit_rights"}
    treaty_event = next(
        event for event in state.events if isinstance(event, EventTreatyLifecycleChanged)
    )
    assert treaty_event.transition == "activated"


def test_foreign_effect_builder_releases_matching_occupations_only() -> None:
    state, _ = _foreign_world(controlled_regions=1, at_war=False)
    regions = pl.concat(
        [
            state.tables["regions"],
            pl.DataFrame([{"id": 5, "owner": "AAA", "controller": "AAA"}]),
        ],
        how="vertical_relaxed",
    )
    state.update_table("regions", regions)
    state.update_table(
        "occupations",
        pl.DataFrame(
            [
                {
                    "region_id": 1,
                    "controller_country_id": "AAA",
                    "occupation_status": "active",
                }
            ],
            schema=state.tables["occupations"].schema,
            strict=False,
        ),
    )

    updates, events = build_foreign_government_effects(state, "AAA", "POL", 12)

    assert updates["regions"].filter(pl.col("id") == 5).item(0, "controller") == "AAA"
    assert updates["occupations"].item(0, "occupation_status") == "ended"
    assert len(events) == 1


def test_foreign_policy_helpers_normalize_scalar_tags_and_invalid_ids() -> None:
    assert _tags(42) == {"42"}
    assert _tags(0) == set()
    assert _integer("not-an-integer") == 0


@pytest.mark.parametrize(
    ("controlled_regions", "at_war", "confirmed"),
    [(3, False, False), (2, False, True), (4, True, True)],
)
def test_unconfirmed_below_threshold_or_hostile_foreign_form_change_is_rejected(
    controlled_regions: int,
    at_war: bool,
    confirmed: bool,
) -> None:
    state, system = _foreign_world(controlled_regions=controlled_regions, at_war=at_war)
    state.current_actions = [
        ActionSetGovernmentForm(
            "player",
            "POL",
            "custom republic",
            "single-party democracy",
            expected_martial_law=False,
            target_martial_law=False,
            confirmed_foreign_change=confirmed,
        )
    ]

    system.update(state, 0.0)

    government = state.tables["country_governments"].filter(
        pl.col("country_id") == "POL"
    ).row(0, named=True)
    assert government["government_form_id"] == "custom republic"
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert state.tables["countries_relations"].get_column("value").to_list() == [-10.0, -10.0]
    assert state.tables["countries_treaties"].is_empty()


def test_foreign_form_action_cannot_change_martial_law() -> None:
    state, system = _foreign_world(controlled_regions=3, at_war=False)
    state.current_actions = [
        ActionSetGovernmentForm(
            "player",
            "POL",
            "custom republic",
            "custom republic",
            expected_martial_law=False,
            target_martial_law=True,
            confirmed_foreign_change=True,
        )
    ]

    system.update(state, 0.0)

    government = state.tables["country_governments"].filter(
        pl.col("country_id") == "POL"
    ).row(0, named=True)
    assert government["martial_law"] is False
    assert state.journal.command_results[-1]["status"] == "rejected"


def _foreign_world(
    *, controlled_regions: int, at_war: bool
) -> tuple[GameState, PoliticalLifecycleSystem]:
    state, system = _world()

    country = dict(state.tables["countries"].row(0, named=True), id="POL", name="Poland")
    state.update_table(
        "countries",
        pl.concat(
            [
                state.tables["countries"],
                pl.DataFrame([country], schema=state.tables["countries"].schema, strict=False),
            ],
            how="vertical",
        ),
    )

    government = dict(
        state.tables["country_governments"].row(0, named=True),
        country_id="POL",
        ruling_party_id="pol-party",
        succession_party_id="pol-party",
        martial_law=False,
    )
    state.update_table(
        "country_governments",
        pl.concat(
            [
                state.tables["country_governments"],
                pl.DataFrame([government], schema=state.tables["country_governments"].schema, strict=False),
            ],
            how="vertical",
        ),
    )

    party = dict(
        state.tables["political_parties"].row(0, named=True),
        country_id="POL",
        party_id="pol-party",
        is_ruling=True,
        eligible=True,
    )
    state.update_table(
        "political_parties",
        pl.concat(
            [
                state.tables["political_parties"],
                pl.DataFrame([party], schema=state.tables["political_parties"].schema, strict=False),
            ],
            how="vertical",
        ),
    )

    state.update_table(
        "countries_relations",
        pl.DataFrame(
            [
                {"source": "POL", "target": "AAA", "value": -10.0},
                {"source": "AAA", "target": "POL", "value": -10.0},
            ]
        ),
    )
    state.update_table(
        "regions",
        pl.DataFrame(
            [
                {
                    "id": region_id,
                    "owner": "POL",
                    "controller": "AAA" if region_id <= controlled_regions else "POL",
                }
                for region_id in range(1, 5)
            ]
        ),
    )
    state.update_table(
        "countries_treaties",
        pl.DataFrame(schema=TREATY_SCHEMA),
    )
    state.update_table(
        "treaty_effects",
        pl.DataFrame(schema=TREATY_EFFECT_SCHEMA),
    )
    state.update_table(
        "countries_wars",
        pl.DataFrame(
            [
                {
                    "side_a": ["AAA"],
                    "side_b": ["POL"],
                    "status": "active" if at_war else "ended",
                }
            ]
        ),
    )
    return state, system
    event = next(event for event in state.events if isinstance(event, EventGovernmentFormChanged))
    assert (event.previous_form_id, event.new_form_id) == (
        "custom republic",
        "single-party democracy",
    )


def test_martial_law_can_change_without_changing_the_government_form() -> None:
    state, system = _world()
    state.current_actions = [
        ActionSetGovernmentForm(
            player_id="player",
            country_tag="AAA",
            expected_form_id="custom republic",
            target_form_id="custom republic",
            expected_martial_law=True,
            target_martial_law=False,
        )
    ]

    system.update(state, 0.0)

    government = state.tables["country_governments"].row(0, named=True)
    assert government["government_form_id"] == "custom republic"
    assert government["martial_law"] is False
    assert state.tables["political_history"].filter(
        pl.col("event_type") == "martial_law_changed"
    ).select("previous_value", "new_value").row(0) == ("active", "inactive")
    event = next(event for event in state.events if isinstance(event, EventMartialLawChanged))
    assert (event.previous_status, event.new_status) == (True, False)
    assert state.journal.command_results[-1]["status"] == "applied"


def test_stale_martial_law_toggle_is_rejected_without_mutating_state() -> None:
    state, system = _world()
    before = state.tables["country_governments"].clone()
    state.current_actions = [
        ActionSetGovernmentForm(
            player_id="player",
            country_tag="AAA",
            expected_form_id="custom republic",
            target_form_id="custom republic",
            expected_martial_law=False,
            target_martial_law=False,
        )
    ]

    system.update(state, 0.0)

    assert state.journal.command_results[-1]["status"] == "rejected"
    assert "martial law changed" in state.journal.command_results[-1]["reason"].casefold()
    assert state.tables["country_governments"].equals(before)
    assert not any(isinstance(event, EventMartialLawChanged) for event in state.events)


@pytest.mark.parametrize(
    ("actor", "expected", "target", "eligible_parties", "crisis", "reason"),
    [
        ("foreign-player", "custom republic", "single-party democracy", 1, "none", "does not control"),
        ("player", "stale form", "single-party democracy", 1, "none", "changed after"),
        ("player", "custom republic", "missing form", 1, "none", "unavailable"),
        ("player", "custom republic", "multi-party democracy", 1, "none", "party count"),
        ("player", "custom republic", "single-party democracy", 1, "active", "crisis"),
    ],
)
def test_invalid_direct_form_change_is_rejected_without_mutating_political_state(
    actor: str,
    expected: str,
    target: str,
    eligible_parties: int,
    crisis: str,
    reason: str,
) -> None:
    state, system = _world(eligible_parties)
    if crisis != "none":
        state.update_table(
            "political_crises",
            pl.DataFrame(
                [{"id": "crisis-1", "country_id": "AAA", "status": crisis}],
                schema=state.tables["political_crises"].schema,
                strict=False,
            ),
        )
    names = (
        "country_governments",
        "political_parties",
        "law_transitions",
        "political_elections",
        "political_history",
    )
    before = {name: state.tables[name].clone() for name in names}
    state.current_actions = [ActionSetGovernmentForm(actor, "AAA", expected, target)]

    system.update(state, 0.0)

    assert state.journal.command_results[-1]["status"] == "rejected"
    assert reason in state.journal.command_results[-1]["reason"].casefold()
    for name, frame in before.items():
        assert state.tables[name].equals(frame), name
    assert not any(isinstance(event, EventGovernmentFormChanged) for event in state.events)
