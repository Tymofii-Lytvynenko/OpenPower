import polars as pl

from modules.base.systems.military.combat_round_resolver import (
    CombatOutcome,
    CombatResolutionPolicy,
    CombatRoundResolver,
)
from modules.base.systems.military.readiness_policy import ReadinessPolicy
from modules.base.systems.military.war_index import ConflictContext


def _resolver(policy=None) -> CombatRoundResolver:
    return CombatRoundResolver(policy or CombatResolutionPolicy(), ReadinessPolicy())


def _conflict() -> ConflictContext:
    return ConflictContext(
        war_id="war-1",
        side_a_members=frozenset({"USA"}),
        side_b_members=frozenset({"CAN"}),
        side_a_tags=frozenset({"USA"}),
        side_b_tags=frozenset({"CAN"}),
    )


def test_resolution_policy_handles_empty_force_and_dominant_defender() -> None:
    policy = CombatResolutionPolicy()

    assert policy.resolve(0, 30) == CombatOutcome(0, 0)
    assert policy.resolve(10, 30) == CombatOutcome(10, 2)


def test_apply_round_returns_surviving_country_on_side_b() -> None:
    class FixedOutcomePolicy:
        def resolve(self, attacker_strength, defender_strength, mode="positional"):
            return CombatOutcome(attacker_losses=20, defender_losses=0)

    units = [
        {"id": "usa-1", "owner": "USA", "strength": 10},
        {"id": "can-1", "owner": "CAN", "strength": 10},
    ]

    winner = _resolver(FixedOutcomePolicy()).apply_combat_round(units, _conflict(), "positional")

    assert winner == "CAN"
    assert units[0]["strength"] == 0
    assert units[1]["strength"] == 10


def test_casualty_records_skip_unknown_owners_and_duplicate_ids() -> None:
    rows = [{"id": "battle-1:2:usa-1"}]
    units = [
        {"id": "usa-1", "owner": "usa", "strength": 5},
        {"id": "can-1", "owner": "can", "strength": 3, "unit_type": "tanks"},
        {"id": "mex-1", "owner": "mex", "strength": 0},
    ]

    _resolver().record_round_casualties(
        rows,
        battle_id="battle-1",
        round_number=2,
        local_units=units,
        conflict=_conflict(),
        pre_round_strength={"usa-1": 10, "can-1": 10, "mex-1": 10},
        now=120,
    )

    assert rows == [
        {"id": "battle-1:2:usa-1"},
        {
            "id": "battle-1:2:can-1",
            "battle_id": "battle-1",
            "unit_id": "can-1",
            "country_id": "CAN",
            "side": "SIDE_B",
            "unit_type": "tanks",
            "losses": 7,
            "round": 2,
            "created_at_minute": 120,
        },
    ]


def test_winning_country_selects_the_stronger_side_b() -> None:
    units = [
        {"owner": "USA", "strength": 4},
        {"owner": "CAN", "strength": 9},
    ]

    assert _resolver().winning_country(units, _conflict()) == "CAN"


def test_damage_eligibility_and_factors_cover_valid_and_empty_sides() -> None:
    resolver = _resolver()
    units = [
        {"id": "usa-1", "owner": "USA", "strength": 100},
        {"id": "can-1", "owner": "CAN", "strength": 50},
    ]

    assert resolver._side_can_damage(units, {"USA"}, {"CAN"})
    assert resolver._side_damage_factor(units, {"USA"}, {"CAN"}) == 1.0
    assert resolver._side_damage_factor([], {"USA"}, {"CAN"}) == 0.0


def test_side_damage_factor_is_zero_when_no_attacker_can_damage_the_defenders() -> None:
    resolver = _resolver()
    resolver.set_capability_index({"usa-1": {"valid_targets": ["ships"]}})
    units = [
        {"id": "usa-1", "owner": "USA", "strength": 10},
        {"id": "can-1", "owner": "CAN", "strength": 10, "unit_type": "tanks"},
    ]

    assert resolver._side_damage_factor(units, {"USA"}, {"CAN"}) == 0.0


def test_capability_target_rules_cover_generic_vulnerability_and_categories() -> None:
    resolver = _resolver()
    resolver.set_capability_index(
        {
            "generic": {
                "valid_targets": ["generic"],
                "capabilities": {"gun_damage": 100, "gun_precision": 1},
            },
            "usa-1": {
                "domain": "land",
                "valid_targets": ["armor"],
                "capabilities": {"gun_damage": 100, "gun_precision": 1},
            },
            "can-air": {"role": "fighters", "domain": "air"},
            "can-tank": {"role": "tanks", "domain": "land", "vulnerabilities": ["land"]},
        }
    )

    assert resolver._attacker_can_damage(
        {"id": "generic"}, {"id": "can-air", "unit_type": "fighter"}
    )
    assert resolver._capability_damage_factor({"id": "generic"}, []) == 1.4
    assert resolver._capability_damage_factor(
        {"id": "usa-1"},
        [
            {"id": "can-air", "unit_type": "fighter"},
            {"id": "can-tank", "unit_type": "tanks"},
        ],
    ) == 1.5

    assert resolver._target_category("fighters", "air") == "air"
    assert resolver._target_category("surface_ships", "naval") == "ships"
    assert resolver._target_category("support", "land") == "support"


def test_projection_loader_uses_empty_defaults_for_malformed_json() -> None:
    resolver = _resolver()
    resolver.load_capability_projections(None)
    assert resolver.capability_index == {}

    resolver.load_capability_projections(
        pl.DataFrame(
            [
                {
                    "unit_id": "usa-1",
                    "role": "tanks",
                    "domain": "AIR",
                    "valid_targets_json": "{invalid",
                    "vulnerabilities_json": "[invalid",
                    "capabilities_json": "{invalid",
                }
            ]
        )
    )

    assert resolver.capability_index["usa-1"] == {
        "role": "tanks",
        "domain": "air",
        "valid_targets": [],
        "vulnerabilities": [],
        "capabilities": {},
    }


def test_empty_casualty_pool_uses_neutral_modifier() -> None:
    assert _resolver()._casualty_modifier([], {"USA"}) == 1.0


def test_loss_distribution_ignores_empty_pool_and_stops_after_requested_losses() -> None:
    resolver = _resolver()
    excluded = {"id": "can-1", "owner": "CAN", "strength": 5}
    resolver._distribute_losses([excluded], {"USA"}, 3)
    assert excluded["strength"] == 5

    units = [
        {"id": "a", "owner": "USA", "strength": 1, "equipment_quantity": 5},
        {"id": "b", "owner": "USA", "strength": 2, "equipment_quantity": 8},
    ]
    resolver._distribute_losses(units, {"USA"}, 1)

    assert units == [
        {"id": "a", "owner": "USA", "strength": 0, "equipment_quantity": 0},
        {"id": "b", "owner": "USA", "strength": 2, "equipment_quantity": 8},
    ]


def test_loss_distribution_skips_a_repeated_unit_reference_after_it_is_depleted() -> None:
    unit = {"id": "usa-1", "owner": "USA", "strength": 1}

    _resolver()._distribute_losses([unit, unit], {"USA"}, total_losses=2)

    assert unit["strength"] == 0
