import polars as pl

from modules.base.systems.world.ai.delegation_context import (
    DelegationContextBuilder,
    _DelegationAccumulator,
    _DelegationScope,
    _DelegationScopePolicy,
    _ResolvedDelegation,
)
from src.shared.state import GameState


def test_accumulator_removes_sphere_targets_when_country_authority_is_unrestricted():
    accumulator = _DelegationAccumulator()
    accumulator.add(
        _ResolvedDelegation(
            "USA",
            _DelegationScope("country", "USA"),
            frozenset({"diplomacy", "economy"}),
        )
    )
    accumulator.add(
        _ResolvedDelegation(
            "USA",
            _DelegationScope("sphere", "trade-union", frozenset({"USA", "CAN"})),
            frozenset({"diplomacy"}),
        )
    )

    assert accumulator.freeze() == (
        {"USA": frozenset({"diplomacy", "economy"})},
        {},
        {},
    )


def test_scope_policy_validates_country_and_sphere_membership():
    policy = _DelegationScopePolicy(
        governments={"USA": "party-a"},
        treaties={
            "active": {"status": " ACTIVE ", "members": '[" usa ", "CAN", " "]'},
            "inactive": {"status": "suspended", "members": ["USA", "CAN"]},
            "invalid-members": {"status": "active", "members": {"USA": True}},
            "single-member": {"status": "active", "members": ["USA"]},
        },
    )

    assert policy.resolve("country", "usa", "USA") == _DelegationScope("country", "usa")
    assert policy.resolve("country", "CAN", "USA") is None
    assert policy.resolve("party", "party-a", "USA") == _DelegationScope("party", "party-a")
    assert policy.resolve("unknown", "scope", "USA") is None
    assert policy._resolve_sphere("missing", "USA") is None
    assert policy._resolve_sphere("inactive", "USA") is None
    assert policy._resolve_sphere("invalid-members", "USA") is None
    assert policy._resolve_sphere("single-member", "USA") is None
    assert policy._resolve_sphere("active", "USA") == _DelegationScope(
        "sphere", "active", frozenset({"USA", "CAN"})
    )
    assert _DelegationScopePolicy._sphere_members({"members": "{"}) == frozenset()


def test_governments_fill_missing_ruling_parties_and_treaties_are_indexed():
    governments = {"USA": "", "CAN": "party-c"}
    parties = pl.DataFrame(
        {
            "country_id": [" usa ", "can", " mex ", " "],
            "party_id": ["Party-A", "Party-B", "Party-M", "Ignored"],
            "is_ruling": [True, True, True, True],
        }
    )

    DelegationContextBuilder._fill_missing_ruling_parties(governments, None)
    DelegationContextBuilder._fill_missing_ruling_parties(governments, parties)

    assert governments == {"USA": "party-a", "CAN": "party-c", "MEX": "party-m"}
    assert DelegationContextBuilder._treaties_by_id(GameState()) == {}
    treaty_state = GameState(
        tables={"countries_treaties": pl.DataFrame({"id": ["trade-union"]})}
    )
    assert DelegationContextBuilder._treaties_by_id(treaty_state) == {
        "trade-union": {"id": "trade-union"}
    }


def test_delegation_resolution_rejects_invalid_owners_and_authority():
    builder = DelegationContextBuilder()
    policy = _DelegationScopePolicy({}, {})
    base_row = {
        "owner_country_id": "USA",
        "active": True,
        "current_controller": "AI",
        "scope_type": "country",
        "scope_id": "USA",
        "authority_json": '[" Economy ", " "]',
    }

    assert builder._resolve_delegation({**base_row, "active": False}, policy) is None
    assert builder._resolve_delegation({**base_row, "authority_json": "{"}, policy) is None
    resolved = builder._resolve_delegation(base_row, policy)

    assert resolved == _ResolvedDelegation(
        "USA", _DelegationScope("country", "USA"), frozenset({"economy"})
    )
    assert DelegationContextBuilder._active_ai_owner({"owner_country_id": "USA"}) is None
    assert DelegationContextBuilder._active_ai_owner(
        {"owner_country_id": "USA", "active": True, "current_controller": "human"}
    ) is None
    assert DelegationContextBuilder._active_ai_owner(
        {"owner_country_id": " usa ", "active": True, "current_controller": " AI "}
    ) == "USA"


def test_authority_rejects_malformed_empty_and_non_list_values():
    assert DelegationContextBuilder._authority({"authority_json": "{"}) is None
    assert DelegationContextBuilder._authority({"authority_json": "{}"}) is None
    assert DelegationContextBuilder._authority({"authority_json": "[]"}) is None
    assert DelegationContextBuilder._authority(
        {"authority_json": '[" diplomacy ", ""]'}
    ) == frozenset({"diplomacy"})
