from __future__ import annotations

import math

from modules.base.systems.demographics.migration_system import MigrationSystem
from modules.base.systems.demographics.population_system import PopulationSystem
from modules.base.systems.economy.budget_system import BudgetSystem
from modules.base.systems.economy.economic_health_system import EconomicHealthSystem
from modules.base.systems.economy.internal_economy_system import InternalEconomySystem
from modules.base.systems.politics.politics_system import PoliticsSystem
from modules.base.systems.world.infrastructure_system import InfrastructureSystem
from modules.base.systems.world.random_event_policy import EVENT_DEFINITIONS, effect_records


def test_every_declared_effect_category_has_an_authoritative_domain_consumer():
    consumers = {
        "health": (PopulationSystem, EconomicHealthSystem, MigrationSystem),
        "labour": (EconomicHealthSystem,),
        "employment": (EconomicHealthSystem,),
        "migration": (MigrationSystem,),
        "approval": (PoliticsSystem,),
        "political_pressure": (MigrationSystem,),
        "production": (InternalEconomySystem,),
        "demand": (InternalEconomySystem,),
        "budget_pressure": (BudgetSystem,),
    }
    declared = {
        effect.category
        for definition in EVENT_DEFINITIONS
        for effect in definition.effects
    }
    assert declared - set(consumers) == {
        effect
        for effect in declared
        if effect.startswith("infrastructure_")
    }
    for category, system_types in consumers.items():
        if category not in declared:
            continue
        assert all(
            "random_event_effects" in system_type.access.reads
            for system_type in system_types
        )
    assert "random_event_effects" in InfrastructureSystem.access.reads


def test_every_supported_event_materializes_finite_bounded_subject_effects():
    for definition in EVENT_DEFINITIONS:
        rows = effect_records(
            event_id=f"acceptance:{definition.event_type}",
            definition=definition,
            severity=1.0,
            region_id=7,
            country_id="AAA",
            starts_at_minute=100,
            expires_at_minute=100 + definition.duration_days * 1_440,
        )
        assert len(rows) == len(definition.effects)
        assert len({row["id"] for row in rows}) == len(rows)
        for row, effect in zip(rows, definition.effects):
            assert row["category"] == effect.category
            assert row["subject_type"] in {"region", "country", "global"}
            assert row["subject_id"] in {"7", "AAA", "world"}
            assert math.isfinite(row["magnitude"])
            assert effect.minimum_magnitude <= row["magnitude"] <= effect.maximum_magnitude
            assert row["starts_at_minute"] == 100
            assert row["expires_at_minute"] == 100 + definition.duration_days * 1_440
