from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from utils.generate_military_personnel_wdi_2001 import build_wdi_personnel_ledger

DATA = Path(__file__).resolve().parents[1] / "modules" / "base" / "data"
MILITARY_PATH = DATA / "countries" / "countries_mil.tsv"
SOURCE_PATH = DATA / "sources" / "2001" / "MS.MIL.TOTL.P1.json"
LEDGER_PATH = DATA / "sources" / "2001" / "military_personnel_wdi_2001.tsv"


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def test_wdi_ledger_reproduces_all_exact_roster_matches_without_overwriting_data() -> None:
    source_bytes = SOURCE_PATH.read_bytes()
    source_payload = json.loads(source_bytes.decode("utf-8-sig"))
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    expected = build_wdi_personnel_ledger(
        source_payload,
        read_tsv(MILITARY_PATH),
        source_hash,
    )
    ledger = read_tsv(LEDGER_PATH)
    military_by_iso3 = {row["id"]: row["military_count"] for row in read_tsv(MILITARY_PATH)}

    assert len(ledger) == len(expected) == 163
    assert ledger == expected
    assert len({row["iso3"] for row in ledger}) == len(ledger)
    assert all(row["military_count"] == military_by_iso3[row["iso3"]] for row in ledger)
    assert all(row["observation_year"] == row["scenario_year"] == "2001" for row in ledger)
    assert all(row["indicator"] == "MS.MIL.TOTL.P1" for row in ledger)
