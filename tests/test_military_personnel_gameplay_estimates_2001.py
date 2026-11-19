from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

import polars as pl

from src.client.ui.panels.military.presenter import MilitaryPresenter
from utils.generate_military_personnel_gameplay_estimates_2001 import (
    EXPECTED_IDS,
    FIELDNAMES,
    SOURCE_PATH,
    build_extension_rows,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = (
    ROOT
    / "modules"
    / "base"
    / "data"
    / "countries"
    / "countries_military_personnel_gameplay_estimates_2001.tsv"
)


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def test_runtime_extension_is_unique_namespaced_and_matches_source_ledger() -> None:
    source_rows = _read_tsv(SOURCE_PATH)
    rows = build_extension_rows(source_rows)
    stored_rows = _read_tsv(OUTPUT_PATH)

    assert {row["id"] for row in rows} == EXPECTED_IDS
    assert len(rows) == len({row["id"] for row in rows}) == 9
    assert rows == stored_rows
    assert set(rows[0]) == set(FIELDNAMES)
    assert all(
        row["gameplay_military_personnel_estimate_2001_available"] == "true"
        for row in rows
    )
    assert all(
        row["gameplay_military_personnel_estimate_2001_display_label"]
        == "Gameplay estimate — not a historical count"
        for row in rows
    )
    assert "military_count" not in rows[0]
    assert not {"available", "quality", "method", "source"}.intersection(rows[0])
    assert all(row["id"] not in {"ATA", "SSD"} for row in rows)


def test_presenter_reads_the_separate_estimate_from_the_country_extension() -> None:
    source_rows = _read_tsv(SOURCE_PATH)
    extension_row = next(
        row for row in build_extension_rows(source_rows) if row["id"] == "PRI"
    )
    state = SimpleNamespace(tables={"countries": pl.DataFrame([extension_row])})

    estimate = MilitaryPresenter().gameplay_personnel_estimate_for_country(state, "PRI")

    assert estimate["value"] == 15_722
    assert estimate["kind"] == "territorial_force_allocation_proxy"
    assert estimate["quality"] == "very_low"
    assert "Puerto Rico" in estimate["note"]
    assert (
        MilitaryPresenter().gameplay_personnel_estimate_for_country(state, "SSD")
        is None
    )


def test_generator_rejects_a_factual_or_duplicate_source_row() -> None:
    source_rows = _read_tsv(SOURCE_PATH)
    source_rows[0] = {**source_rows[0], "historical_observation": "yes"}
    try:
        build_extension_rows(source_rows)
    except ValueError as exc:
        assert "invalid historical_observation" in str(exc)
    else:
        raise AssertionError(
            "A gameplay estimate must not be promoted to a historical observation."
        )

    source_rows = _read_tsv(SOURCE_PATH)
    try:
        build_extension_rows([*source_rows, source_rows[0]])
    except ValueError as exc:
        assert "Duplicate gameplay personnel estimate" in str(exc)
    else:
        raise AssertionError(
            "Duplicate country estimates must be rejected before joining the extension."
        )
