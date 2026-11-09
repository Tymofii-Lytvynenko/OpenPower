from types import SimpleNamespace

import polars as pl

from src.client.ui.panels.politics.relations_presenter import (
    RelationCountryOption,
    RelationsPresenter,
)


def state_with(tables=None):
    return SimpleNamespace(tables=tables or {})


class HistoryQueries:
    def __init__(self, timeline):
        self.timeline = timeline
        self.calls = []

    def relationship_timeline(self, state, country_a, country_b):
        self.calls.append((state, country_a, country_b))
        return self.timeline


def test_relation_countries_select_names_sort_and_skip_invalid_rows():
    presenter = RelationsPresenter()
    assert RelationCountryOption("USA", "United States").label == "United States (USA)"
    assert presenter.countries(state_with()) == ()
    assert presenter.countries(state_with({"countries": pl.DataFrame(schema={"id": pl.String})})) == ()
    assert presenter.countries(state_with({"countries": pl.DataFrame({"name": ["Missing id"]})})) == ()

    rows = presenter.countries(state_with({
        "countries": pl.DataFrame({
            "id": ["usa", "can", ""], "name": ["Zeta", "Alpha", "Blank"],
        })
    }))
    assert [(row.tag, row.name) for row in rows] == [("CAN", "Alpha"), ("USA", "Zeta")]

    country_name = presenter.countries(state_with({
        "countries": pl.DataFrame({"id": ["can"], "country_name": ["Canada"]})
    }))
    display_name = presenter.countries(state_with({
        "countries": pl.DataFrame({"id": ["mex"], "display_name": ["Mexico"]})
    }))
    id_name = presenter.countries(state_with({"countries": pl.DataFrame({"id": ["arg"]})}))
    assert country_name[0].name == "Canada"
    assert display_name[0].name == "Mexico"
    assert id_name[0].name == "arg"


def test_build_pair_validates_countries_and_projects_only_relation_history():
    timeline = [
        {"timeline_kind": "relation_value", "game_minute": 10, "value": 25.0},
        {"timeline_kind": "relation_value", "game_minute": None, "value": "bad"},
        {"timeline_kind": "other", "game_minute": 11, "value": 99.0},
        {"timeline_kind": "relation_value", "game_minute": 12, "value": None},
    ]
    queries = HistoryQueries(timeline)
    presenter = RelationsPresenter(queries)
    state = state_with({
        "countries": pl.DataFrame({"id": ["USA", "CAN"], "name": ["United States", "Canada"]}),
        "countries_relations": pl.DataFrame({"source": ["usa"], "target": ["can"], "value": [18.5]}),
    })

    assert presenter.build_pair(state, "unknown", "CAN") is None
    assert presenter.build_pair(state, "USA", "USA") is None
    pair = presenter.build_pair(state, " usa ", "can")

    assert pair is not None
    assert pair.country_a.label == "United States (USA)"
    assert pair.country_b.label == "Canada (CAN)"
    assert pair.current_value == 18.5
    assert pair.history == ((10, 25.0), (0, 0.0))
    assert queries.calls == [(state, "USA", "CAN")]


def test_current_relation_value_handles_missing_schema_and_unusable_samples():
    get_value = RelationsPresenter._current_value
    assert get_value(state_with(), "USA", "CAN") is None
    assert get_value(
        state_with({"countries_relations": pl.DataFrame(schema={"source": pl.String})}),
        "USA",
        "CAN",
    ) is None
    assert get_value(
        state_with({"countries_relations": pl.DataFrame({"source": ["USA"]})}),
        "USA",
        "CAN",
    ) is None
    assert get_value(
        state_with({"countries_relations": pl.DataFrame({
            "source": ["MEX"], "target": ["CAN"], "value": [50.0],
        })}),
        "USA",
        "CAN",
    ) is None
    assert get_value(
        state_with({"countries_relations": pl.DataFrame({
            "source": ["USA"], "target": ["CAN"], "value": ["not-a-number"],
        })}),
        "USA",
        "CAN",
    ) is None
