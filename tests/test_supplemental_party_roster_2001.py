from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl

import src.client.ui.panels.country_more_info as country_info_module
from modules.base.schema import build_base_schema_registry
from src.client.ui.panels.country_more_info import (
    CountryMoreInfoPanel,
    CountryMoreInfoPresenter,
)
from src.server.io.data_load_manager import DataLoader
from src.shared.config import GameConfig
from src.shared.state import GameState

ROOT = Path(__file__).resolve().parents[1]


def test_supplemental_party_rows_are_separate_cited_and_schema_valid() -> None:
    tables = DataLoader(GameConfig(ROOT))._load_world_tables()
    roster = tables["country_party_roster_supplemental_2001"]
    counts = {
        country_id: roster.filter(pl.col("country_id") == country_id).height
        for country_id in ("KOS", "MNE", "PSE", "SRB", "SSD", "TLS")
    }

    assert counts == {"KOS": 14, "MNE": 16, "PSE": 2, "SRB": 4, "SSD": 1, "TLS": 12}
    assert set(roster["source_year"].to_list()) == {1996, 2000, 2001}
    assert set(roster["leader_status"].to_list()) == {"not_reported", "reported"}
    assert roster["leaders_text"].null_count() == 0
    assert not {"support_share", "vote_share", "votes", "is_ruling"}.intersection(
        roster.columns
    )
    assert roster.filter(pl.col("source_url").str.contains("osce.org")).height == 30
    assert (
        roster.filter(pl.col("source_url").str.contains("peacekeeping.un.org")).height
        == 12
    )

    manifest = json.loads(
        (
            ROOT
            / "modules/base/data/sources/2001/country_party_roster_supplemental_2001.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["record_count"] == 49
    assert manifest["country_counts"] == counts

    spla = roster.filter(pl.col("country_id") == "SSD")
    assert spla["display_name"][0] == "Sudan People's Liberation Army"
    assert spla["source_field"][0] == "Political pressure groups and leaders"
    assert spla["leader_status"][0] == "reported"
    assert spla["leaders_text"][0] == "Dr. John GARANG"
    assert "not a separate South Sudan party roster or election result" in spla["source_note"][0]

    state = GameState()
    state.update_table("country_party_roster_supplemental_2001", roster)
    registry = build_base_schema_registry()
    registry.ensure_state(state)
    assert registry.validate_state(state) == []
    assert registry.get("country_party_roster_supplemental_2001").key_columns == ("id",)


def test_srb_and_pse_records_keep_actual_election_year_and_scope() -> None:
    tables = DataLoader(GameConfig(ROOT))._load_world_tables()
    roster = tables["country_party_roster_supplemental_2001"]
    srb_rows = roster.filter(pl.col("country_id") == "SRB")
    pse_rows = roster.filter(pl.col("country_id") == "PSE")

    assert set(srb_rows["source_year"].to_list()) == {2000}
    assert set(srb_rows["display_name"].to_list()) == {
        "Democratic Opposition of Serbia (DOS)",
        "Socialist Party of Serbia",
        "Serbian Radical Party",
        "Party of Serbian Unity",
    }
    assert set(pse_rows["source_year"].to_list()) == {1996}
    assert set(pse_rows["display_name"].to_list()) == {
        "Fatah (Palestine Liberation Movement)",
        "Independent Fatah",
    }
    assert all(
        "not a complete 2001 party roster" in note
        for note in pse_rows["source_note"].to_list()
    )
    assert set(srb_rows["leader_status"].to_list()) == {"not_reported"}
    assert set(pse_rows["leader_status"].to_list()) == {"not_reported"}


def test_country_info_presenter_exposes_srb_and_pse_supplemental_records() -> None:
    tables = DataLoader(GameConfig(ROOT))._load_world_tables()
    tables["countries"] = pl.DataFrame(
        {
            "id": ["PSE", "SRB"],
            "name": ["Palestine", "Serbia"],
            "human_dev": [0.5, 0.5],
        }
    )
    tables["regions"] = pl.DataFrame(
        {
            "id": [1, 2],
            "owner": ["PSE", "SRB"],
            "controller": ["PSE", "SRB"],
            "area_km2": [100.0, 100.0],
            "pop_14": [100, 100],
            "pop_15_64": [800, 800],
            "pop_65": [100, 100],
        }
    )

    palestine = CountryMoreInfoPresenter().build(
        SimpleNamespace(globals={}, tables=tables), "PSE"
    ).party_roster_2001
    serbia = CountryMoreInfoPresenter().build(
        SimpleNamespace(globals={}, tables=tables), "SRB"
    ).party_roster_2001

    assert [entry.display_name for entry in palestine.supplemental_entries] == [
        "Fatah (Palestine Liberation Movement)",
        "Independent Fatah",
    ]
    assert all("1996" in entry.source_reference for entry in palestine.supplemental_entries)
    assert [entry.display_name for entry in serbia.supplemental_entries] == [
        "Democratic Opposition of Serbia (DOS)",
        "Socialist Party of Serbia",
        "Serbian Radical Party",
        "Party of Serbian Unity",
    ]
    assert all("2000" in entry.source_reference for entry in serbia.supplemental_entries)


def test_ssd_spla_context_retains_scope_caveat_in_the_roster_dialog(monkeypatch) -> None:
    tables = DataLoader(GameConfig(ROOT))._load_world_tables()
    tables["countries"] = pl.DataFrame(
        {"id": ["SSD"], "name": ["South Sudan"], "human_dev": [0.5]}
    )
    tables["regions"] = pl.DataFrame(
        {
            "id": [1],
            "owner": ["SSD"],
            "controller": ["SSD"],
            "area_km2": [100.0],
            "pop_14": [100],
            "pop_15_64": [800],
            "pop_65": [100],
        }
    )
    model = CountryMoreInfoPresenter().build(
        SimpleNamespace(globals={}, tables=tables), "SSD"
    )
    roster = model.party_roster_2001

    assert roster.status == "no_separate_country_entry"
    assert roster.entries == ()
    assert len(roster.supplemental_entries) == 1
    entry = roster.supplemental_entries[0]
    assert entry.leaders_text == "Dr. John GARANG"
    assert "southern-Sudan political-movement context" in entry.source_note
    assert "not a separate South Sudan party roster or election result" in entry.source_note

    ui = SimpleNamespace(
        button=Mock(return_value=False),
        begin_child=Mock(return_value=True),
        end_child=Mock(),
        get_io=Mock(return_value=SimpleNamespace(
            display_size=SimpleNamespace(x=1000.0, y=800.0)
        )),
        separator_text=Mock(),
        text_wrapped=Mock(),
        text_disabled=Mock(),
    )
    monkeypatch.setattr(country_info_module, "imgui", ui)
    CountryMoreInfoPanel()._render_party_roster_content(model)

    rendered_text = "\n".join(
        str(call.args[0]) for call in ui.text_wrapped.call_args_list if call.args
    )
    assert entry.source_note in rendered_text


def test_country_info_shows_supplementary_kosovo_citations_separately(
    monkeypatch,
) -> None:
    tables = DataLoader(GameConfig(ROOT))._load_world_tables()
    tables["countries"] = pl.DataFrame(
        {"id": ["KOS"], "name": ["Kosovo"], "human_dev": [0.5]}
    )
    tables["regions"] = pl.DataFrame(
        {
            "id": [1],
            "owner": ["KOS"],
            "controller": ["KOS"],
            "area_km2": [100.0],
            "pop_14": [100],
            "pop_15_64": [800],
            "pop_65": [100],
        }
    )
    model = CountryMoreInfoPresenter().build(
        SimpleNamespace(globals={}, tables=tables), "KOS"
    )
    roster = model.party_roster_2001

    assert roster.status == "no_separate_country_entry"
    assert roster.entries == ()
    assert len(roster.supplemental_entries) == 14
    assert (
        roster.supplemental_entries[0].source_name
        == "OSCE Mission in Kosovo and Kosovo Central Election Commission"
    )

    ui = SimpleNamespace(
        button=Mock(return_value=False),
        begin_child=Mock(return_value=True),
        end_child=Mock(),
        get_io=Mock(
            return_value=SimpleNamespace(
                display_size=SimpleNamespace(x=1000.0, y=800.0)
            )
        ),
        separator_text=Mock(),
        text_wrapped=Mock(),
        text_disabled=Mock(),
    )
    monkeypatch.setattr(country_info_module, "imgui", ui)

    CountryMoreInfoPanel()._render_party_roster_content(model)

    assert any(
        call.kwargs.get("test_id") == "country.info.party_roster.supplemental.entry.0"
        and "Democratic League of Kosovo" in call.args[0]
        for call in ui.text_wrapped.call_args_list
    )
    assert any(
        call.kwargs.get("test_id") == "country.info.party_roster.supplemental.url.0"
        and "omik.osce.org/kosovo/54021" in call.args[0]
        for call in ui.text_wrapped.call_args_list
    )
    assert any(
        "not CIA Factbook" in call.args[0] for call in ui.separator_text.call_args_list
    )


def test_factbook_source_rows_and_coverage_remain_unchanged() -> None:
    factbook_manifest = json.loads(
        (
            ROOT
            / "modules/base/data/sources/2001/country_party_roster_factbook_2001.json"
        ).read_text(encoding="utf-8")
    )
    with (
        ROOT / "modules/base/data/sources/2001/country_party_roster_factbook_2001.tsv"
    ).open(encoding="utf-8-sig", newline="") as stream:
        factbook_rows = list(csv.DictReader(stream, delimiter="\t"))

    assert factbook_manifest["counts"]["party_record_count"] == 1385
    assert len(factbook_rows) == 1385
    assert {row["source_name"] for row in factbook_rows} == {
        "United States Central Intelligence Agency, The World Factbook 2001"
    }
