import polars as pl

from modules.base.systems.world.annexation_policy import AnnexationPolicy
from src.shared.state import GameState


def test_invalidated_claim_regions_handles_missing_regions_and_pending_claims() -> None:
    policy = AnnexationPolicy()
    assert policy.invalidated_claim_regions(GameState(), pl.DataFrame()) == set()

    state = GameState(
        tables={
            "regions": pl.DataFrame(
                {
                    "id": [1, 2, 3],
                    "owner": ["AAA", "CCC", "BBB"],
                    "controller": ["BBB", "BBB", "BBB"],
                    "adjacent_region_ids": ["[]", "[1, 3]", "[]"],
                }
            )
        }
    )
    claims = pl.DataFrame(
        {
            "status": ["pending", "pending", "approved"],
            "region_id": [1, 2, 3],
            "political_owner_id": ["AAA", "AAA", "BBB"],
            "annexing_country_id": ["BBB", "BBB", "BBB"],
        }
    )

    assert policy.invalidated_claim_regions(state, claims) == {1, 2, 3}


def test_neighbor_lookup_uses_explicit_adjacency_in_both_directions() -> None:
    state = GameState(
        tables={
            "region_adjacency": pl.DataFrame(
                {
                    "region_id": [2, 1],
                    "neighbor_region_id": [3, 2],
                }
            )
        }
    )

    assert AnnexationPolicy()._neighbor_regions(state, {2}) == {1, 3}
    assert AnnexationPolicy()._neighbor_regions(state, set()) == set()


def test_inline_neighbor_lookup_handles_missing_and_encoded_adjacency() -> None:
    policy = AnnexationPolicy()

    assert policy._inline_neighbors(None, {1}) == set()
    assert policy._inline_neighbors(pl.DataFrame({"id": [1]}), {1}) == set()
    assert policy._inline_neighbors(
        pl.DataFrame({"id": [1, 2], "adjacent_region_ids": ["[2, 3]", "[]"]}),
        {1},
    ) == {2, 3}


def test_region_id_parser_accepts_collections_and_handles_bad_json() -> None:
    policy = AnnexationPolicy()

    assert policy._ids(["1", "bad", -2, ""]) == {1, -2}
    assert policy._ids("not-json") == set()
    assert policy._ids("[3, \"4\", \"bad\"]") == {3, 4}
