from types import SimpleNamespace

import polars as pl

from src.client.ui.panels.politics.presenter import PoliticsPresenter


def state_with(tables=None):
    return SimpleNamespace(tables=tables or {})


def test_build_summary_projects_country_government_and_capital_data():
    state = state_with({
        "countries": pl.DataFrame({
            "id": ["USA"], "gvt_approval": [0.72], "gvt_stability": [65.0], "gvt_corruption": [0.1],
        }),
        "country_governments": pl.DataFrame({
            "country_id": ["USA"], "government_type": ["Republic"], "ideology_balance": [0.7],
            "capital_region_id": [1], "next_election": ["2040"], "martial_law": [False],
            "election_risk": [0.2],
        }),
        "regions": pl.DataFrame({"id": [1], "name": ["Capital City"]}),
    })

    summary = PoliticsPresenter().build_summary(state, "USA")

    assert summary.government_type == "Republic"
    assert summary.ideology_balance == 0.7
    assert summary.approval_pct == 72.0
    assert summary.stability_pct == 65.0
    assert summary.corruption_pct == 10.0
    assert summary.capital_name == "Capital City"
    assert summary.next_election == "2040"
    assert summary.election_risk_pct == 20.0


def test_laws_filter_and_sort_country_rows_and_tolerate_missing_sources():
    presenter = PoliticsPresenter()
    assert presenter.laws_for_country(state_with(), "USA") == []
    assert presenter.laws_for_country(
        state_with({"country_laws": pl.DataFrame(schema={"country_id": pl.String})}), "USA"
    ) == []
    assert presenter.laws_for_country(
        state_with({"country_laws": pl.DataFrame({"title": ["No country field"]})}), "USA"
    ) == []

    rows = pl.DataFrame({
        "country_id": ["USA", "USA", "CAN"],
        "group_name": ["Economy", "Economy", "Health"],
        "title": ["Tax", "Budget", "Care"],
        "value": ["low", "high", "public"],
    })
    assert [row["title"] for row in presenter.laws_for_country(
        state_with({"country_laws": rows}), "USA"
    )] == ["Budget", "Tax"]


def test_treaty_membership_falls_back_to_sides_and_averages_peer_relations():
    presenter = PoliticsPresenter()
    assert presenter.active_treaties_for_country(state_with(), "USA") == []
    assert presenter.active_treaties_for_country(
        state_with({"countries_treaties": pl.DataFrame(schema={"status": pl.String})}), "USA"
    ) == []

    treaties = pl.DataFrame({
        "id": ["treaty-1", "treaty-2", "inactive", "foreign"],
        "name": ["Alpha Pact", None, "Old Pact", "Far Pact"],
        "type": ["pact", None, "pact", "pact"],
        "status": ["active", None, "inactive", "active"],
        "members": ["USA,CAN", "", "USA,CAN", "MEX,CAN"],
        "side_a": ["USA", "USA,MEX", "USA", "MEX"],
        "side_b": ["CAN", "ARG", "CAN", "CAN"],
        "open_to_new_members": [True, False, True, True],
    })
    relations = pl.DataFrame({
        "source": ["USA", "USA", "USA"],
        "target": ["CAN", "MEX", "ARG"],
        "value": [6.0, 2.0, 4.0],
    })
    state = state_with({"countries_treaties": treaties, "countries_relations": relations})

    rows = presenter.active_treaties_for_country(state, "USA")

    assert [row["id"] for row in rows] == ["treaty-2", "treaty-1"]
    assert rows[0]["members"] == ("ARG", "MEX", "USA")
    assert rows[0]["members_count"] == 3
    assert rows[0]["relation_score"] == 3.0
    assert rows[1]["relation_score"] == 6.0
    assert rows[1]["open_to_new_members"] is True


def test_pending_treaties_include_source_or_required_participant_in_newest_order():
    presenter = PoliticsPresenter()
    assert presenter.pending_treaties_for_country(state_with(), "USA") == []
    assert presenter.pending_treaties_for_country(
        state_with({"pending_treaties": pl.DataFrame(schema={"source_country_id": pl.String})}), "USA"
    ) == []

    pending = pl.DataFrame({
        "id": ["new", "old", "other"],
        "source_country_id": ["CAN", "USA", "MEX"],
        "required_responses": ["USA,CAN", "CAN", "ARG"],
        "created_at": ["2026-02", "2025-11", "2026-03"],
    })

    rows = presenter.pending_treaties_for_country(state_with({"pending_treaties": pending}), "USA")
    assert [row["id"] for row in rows] == ["new", "old"]


def test_preferred_partners_validate_schema_limit_results_and_resolve_names():
    presenter = PoliticsPresenter()
    assert presenter.preferred_treaty_partners(state_with(), "USA") == []
    assert presenter.preferred_treaty_partners(
        state_with({"countries_relations": pl.DataFrame({"source": ["USA"]})}), "USA"
    ) == []

    state = state_with({
        "countries": pl.DataFrame({"id": ["CAN", "MEX"], "name": ["Canada", "Mexico"]}),
        "countries_relations": pl.DataFrame({
            "source": ["USA", "USA", "CAN"], "target": ["MEX", "CAN", "USA"],
            "value": [8.0, 5.0, 100.0],
        }),
    })
    rows = presenter.preferred_treaty_partners(state, "USA", limit=1)

    assert rows == [{"country_tag": "MEX", "country_name": "Mexico", "relation_score": 8.0}]


def test_average_relations_and_government_lookup_cover_unavailable_inputs():
    presenter = PoliticsPresenter()
    assert presenter.average_relation_score(state_with(), "USA", ["CAN"]) == 0.0
    assert presenter.average_relation_score(state_with(), "USA", []) == 0.0
    assert presenter.average_relation_score(
        state_with({"countries_relations": pl.DataFrame({"source": ["USA"]})}), "USA", ["CAN"]
    ) == 0.0

    relations = pl.DataFrame({
        "source": ["USA", "USA", "USA"], "target": ["CAN", "MEX", "ARG"],
        "value": [4.0, 8.0, 99.0],
    })
    state = state_with({"countries_relations": relations})
    assert presenter.average_relation_score(state, "USA", ["CAN", "MEX"]) == 6.0
    assert presenter.average_relation_score(state, "USA", ["FRA"]) == 0.0

    assert presenter._government_row(state_with(), "USA") == {}
    assert presenter._government_row(
        state_with({"country_governments": pl.DataFrame(schema={"country_id": pl.String})}), "USA"
    ) == {}
    assert presenter._government_row(
        state_with({"country_governments": pl.DataFrame({"government_type": ["Republic"]})}), "USA"
    ) == {}
    governments = pl.DataFrame({"country_id": ["CAN", "USA"], "government_type": ["Monarchy", "Republic"]})
    assert presenter._government_row(state_with({"country_governments": governments}), "USA")["government_type"] == "Republic"
    assert presenter._government_row(state_with({"country_governments": governments}), "MEX") == {}
