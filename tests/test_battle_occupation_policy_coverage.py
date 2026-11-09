from typing import Any, Iterable

from modules.base.systems.military.battle_occupation_policy import (
    BattleOccupationPolicy,
)
from modules.base.systems.military.battle_victory_finalizer import (
    ConcludedOccupationUpdateRequest,
)
from modules.base.systems.military.war_index import WarIndex, WarRecord


class _StrengthResolver:
    def total_strength(
        self,
        local_units: list[dict[str, Any]],
        eligible_tags: Iterable[str],
    ) -> int:
        eligible = set(eligible_tags)
        return sum(
            int(unit.get("strength") or 0)
            for unit in local_units
            if unit.get("owner") in eligible
        )

    def raw_strength(
        self,
        local_units: list[dict[str, Any]],
        eligible_tags: Iterable[str],
    ) -> int:
        return self.total_strength(local_units, eligible_tags)


def _policy() -> BattleOccupationPolicy:
    return BattleOccupationPolicy(_StrengthResolver())


def test_no_victor_marks_only_the_matching_occupation_contested() -> None:
    occupations = [
        {
            "region_id": 1,
            "contested": False,
            "occupation_status": "active",
            "updated_at_minute": 10,
        },
        {
            "region_id": 2,
            "contested": False,
            "occupation_status": "active",
            "updated_at_minute": 20,
        },
    ]
    request = ConcludedOccupationUpdateRequest(
        region_id=1,
        victor="",
        unit_rows=[],
        region_rows=[],
        occupation_rows=occupations,
        now=30,
    )

    updated = _policy().update_concluded_occupation(request)

    assert updated[0]["contested"] is True
    assert updated[0]["occupation_status"] == "contested"
    assert updated[0]["updated_at_minute"] == 30
    assert updated[1]["contested"] is False


def test_nonpositive_victor_garrison_strength_is_not_counted() -> None:
    request = ConcludedOccupationUpdateRequest(
        region_id=1,
        victor="AAA",
        unit_rows=[
            {
                "current_region_id": 1,
                "owner": "AAA",
                "strength": 0,
                "is_moving": False,
            }
        ],
        region_rows=[{"id": 1, "controller": "OLD"}],
        occupation_rows=[],
        now=30,
    )

    updated = _policy().update_concluded_occupation(request)

    assert updated[0]["controller_country_id"] == "AAA"
    assert updated[0]["garrison_strength"] == 0


def test_unchanged_occupation_row_reuses_the_previous_record() -> None:
    previous = {
        "region_id": 7,
        "controller_country_id": "AAA",
        "garrison_strength": 10,
        "resistance": 0.0,
        "occupation_status": "active",
        "started_at_minute": 3,
        "updated_at_minute": 4,
        "contested": False,
    }

    result = _policy().occupation_row(
        region_id=7,
        occupier="AAA",
        local_units=[{"owner": "AAA", "strength": 10}],
        now=30,
        previous=previous,
    )

    assert result is previous


def test_candidate_returns_none_when_units_have_no_valid_owner() -> None:
    result = _policy().occupation_candidate(
        local_units=[{"owner": "", "strength": 10}],
        current_controller="BBB",
        wars=WarIndex([]),
    )

    assert result is None


def test_candidate_is_blocked_by_a_hostile_local_owner() -> None:
    wars = WarIndex(
        [
            WarRecord(
                war_id="current-control",
                side_a=frozenset({"AAA"}),
                side_b=frozenset({"CCC"}),
                status="active",
            ),
            WarRecord(
                war_id="local-opposition",
                side_a=frozenset({"AAA"}),
                side_b=frozenset({"BBB"}),
                status="active",
            ),
        ]
    )

    result = _policy().occupation_candidate(
        local_units=[
            {"owner": "AAA", "strength": 100},
            {"owner": "BBB", "strength": 60},
        ],
        current_controller="CCC",
        wars=wars,
    )

    assert result is None
