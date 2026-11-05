from types import SimpleNamespace

from modules.base.systems.military.covert_mission_effects import (
    MissionEffectServices,
    apply_mission_effect,
)
from src.shared.covert_mission_options import mission_effect_modifier


def _services():
    def finite_number(value):
        try:
            return float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0

    def unexpected(*_args, **_kwargs):
        raise AssertionError("This effect path should not access unit tables.")

    def adjust_relations(rows, source, target, delta):
        rows.append(
            {"source": source, "target": target, "delta": delta}
        )

    return MissionEffectServices(
        normalize_tag=lambda value: str(value or "").strip().upper(),
        finite_number=finite_number,
        sabotage_unit_candidates=unexpected,
        write_frame_if_changed=unexpected,
        adjust_relations=adjust_relations,
    )


def test_coup_effect_uses_injected_country_services_and_applies_attribution_penalty():
    state = SimpleNamespace(tables={})
    target = {"id": "CAN"}
    government = {"country_id": "CAN", "election_risk": 0.4, "ideology_balance": 0.2}
    governments = [government]
    relations = []
    scale = mission_effect_modifier("medium", partial=True)

    apply_mission_effect(
        state,
        {"mission_type": "coup_attempt", "complexity": "medium"},
        target,
        {},
        governments,
        relations,
        "usa",
        partial=True,
        outcome="partial_success",
        services=_services(),
    )

    assert government["election_risk"] == 0.4 + 0.08 * scale
    assert government["ideology_balance"] == 0.2 + 0.025 * scale
    assert relations == [{"source": "USA", "target": "CAN", "delta": -10.0}]


def test_failed_attributed_mission_skips_world_effect_but_keeps_diplomatic_penalty():
    state = SimpleNamespace(tables={})
    target = {"id": "CAN", "security_upkeep": 10.0, "gdp": 100.0}
    government = {"country_id": "CAN", "election_risk": 0.4, "ideology_balance": 0.2}
    relations = []

    apply_mission_effect(
        state,
        {"mission_type": "terrorism", "complexity": "medium"},
        target,
        {},
        [government],
        relations,
        "USA",
        outcome="failure",
        services=_services(),
    )

    assert target["security_upkeep"] == 10.0
    assert government["election_risk"] == 0.4
    assert relations == [{"source": "USA", "target": "CAN", "delta": -12.0}]
