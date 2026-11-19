import csv
import unittest
from datetime import datetime
from pathlib import Path

from src.server.io.static_loader import StaticAssetLoader
from src.shared.config import GameConfig
from src.shared.state import GAME_EPOCH
from src.shared.treaties import treaty_definition


class TestWorld2001TreatyAndWarData(unittest.TestCase):
    def setUp(self):
        self.project_root = Path(__file__).resolve().parent.parent
        self.tables = StaticAssetLoader(GameConfig(self.project_root))._load_toml_collection("world")

    def test_scenario_epoch_and_war_records_are_explicit_and_actionable(self):
        self.assertEqual(GAME_EPOCH, datetime(2001, 1, 1, 0, 0))
        wars = self.tables["countries_wars"].to_dicts()
        wars_by_id = {row["id"]: row for row in wars}

        self.assertEqual(
            set(wars_by_id),
            {
                "second_congo_war",
                "second_intifada",
                "kashmir_conflict",
                "sierra_leone_civil_war",
                "mano_river_border_conflict",
                "sudan_uganda_proxy_conflict",
            },
        )
        self.assertEqual(len(wars), len(wars_by_id))
        for row in wars:
            self.assertTrue(row["name"])
            self.assertEqual(row["status"], "active")
            self.assertTrue(row["side_a"])
            self.assertTrue(row["side_b"])

        congo = wars_by_id["second_congo_war"]
        self.assertEqual(set(congo["side_a"]), {"COD", "AGO", "NAM", "ZWE"})
        self.assertEqual(set(congo["side_b"]), {"RWA", "UGA", "BDI"})
        self.assertNotIn("TCD", congo["side_a"])
        self.assertFalse(any(set(row["side_a"]) == {"USA", "GBR"} and row["side_b"] == ["IRQ"] for row in wars))
        self.assertFalse(any(row["side_a"] == ["ERI"] and row["side_b"] == ["ETH"] for row in wars))

    def test_2001_treaty_memberships_and_consultative_records_are_preserved(self):
        treaties = {row["id"]: row for row in self.tables["countries_treaties"].to_dicts()}

        self.assertEqual(
            set(treaties["rio_pact"]["members"]),
            {
                "ARG", "BHS", "BOL", "BRA", "CHL", "COL", "CRI", "CUB", "DOM", "ECU",
                "SLV", "GTM", "HTI", "HND", "MEX", "NIC", "PAN", "PRY", "PER", "USA", "URY", "VEN",
            },
        )
        self.assertNotIn("TTO", treaties["rio_pact"]["members"])
        self.assertIn("1986-09-17", treaties["anzus"]["terms"])

        self.assertNotIn("us_thailand_major_ally", treaties)
        expected_members = {
            "seato_manila_pact": {"AUS", "FRA", "NZL", "PHL", "THA", "GBR", "USA"},
            "fpda": {"AUS", "MYS", "NZL", "SGP", "GBR"},
        }
        for treaty_id, members in expected_members.items():
            treaty = treaties[treaty_id]
            self.assertEqual(set(treaty["members"]), members)
            self.assertEqual(treaty["status"], "active")
            self.assertEqual(treaty_definition(treaty["type"]), None)
            self.assertIn("no automatic OpenPower defense effects", treaty["terms"])

        historical_members = {
            "china_dprk_mutual_assistance": {"CHN", "PRK"},
            "arab_league_joint_defense": {"EGY", "IRQ", "JOR", "LBN", "SAU", "SYR", "YEM"},
            "weu_modified_brussels_treaty": {"BEL", "FRA", "DEU", "GRC", "ITA", "LUX", "NLD", "PRT", "ESP", "GBR"},
            "france_cameroon_defense": {"CMR", "FRA"},
            "france_central_african_defense": {"CAF", "FRA"},
            "france_comoros_defense_cooperation": {"COM", "FRA"},
            "france_togo_defense": {"FRA", "TGO"},
            "france_uae_defense_cooperation": {"ARE", "FRA"},
            "france_kuwait_defense_cooperation": {"FRA", "KWT"},
            "france_qatar_defense_cooperation": {"FRA", "QAT"},
        }
        for treaty_id, members in historical_members.items():
            treaty = treaties[treaty_id]
            self.assertEqual(set(treaty["members"]), members)
            self.assertNotEqual(treaty.get("status"), "active")
            self.assertIsNone(treaty_definition(treaty["type"]))
            self.assertIn("automatic OpenPower", treaty["terms"])

    def test_treaty_and_war_edits_have_per_record_provenance(self):
        ledger_path = self.project_root / "modules" / "base" / "data" / "sources" / "2001" / "world_conflicts_treaties_2001.tsv"
        with ledger_path.open(encoding="utf-8", newline="") as ledger_file:
            ledger = list(csv.DictReader(ledger_file, delimiter="\t"))

        records = {row["record_id"] for row in ledger}
        required_records = {
            "anzus",
            "rio_pact",
            "seato_manila_pact",
            "fpda",
            "us_thailand_major_ally",
            "second_congo_war",
            "second_intifada",
            "kashmir_conflict",
            "sierra_leone_civil_war",
            "mano_river_border_conflict",
            "sudan_uganda_proxy_conflict",
            "legacy_war_usa_gbr_irq",
            "legacy_war_eri_eth",
            "china_dprk_mutual_assistance",
            "arab_league_joint_defense",
            "weu_modified_brussels_treaty",
            "france_cameroon_defense",
            "france_central_african_defense",
            "france_comoros_defense_cooperation",
            "france_togo_defense",
            "france_uae_defense_cooperation",
            "france_kuwait_defense_cooperation",
            "france_qatar_defense_cooperation",
        }
        self.assertTrue(required_records.issubset(records))
        for row in ledger:
            self.assertEqual(row["scenario_date"], "2001-01-01")
            self.assertTrue(row["source_url"])
            self.assertTrue(row["notes"])


if __name__ == "__main__":
    unittest.main()
