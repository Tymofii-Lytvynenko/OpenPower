import shutil
import unittest
from pathlib import Path
from uuid import uuid4

import polars as pl

from src.server.io.data_load_manager import DataLoader
from src.shared.config import GameConfig


class TestDataLoaderModLayering(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(__file__).resolve().parent.parent / ".temp"
        self.temp_root.mkdir(exist_ok=True)

    def test_layered_mod_data_merges_and_overrides(self):
        project_root = self.temp_root / f"loader-test-{uuid4().hex}"
        project_root.mkdir(parents=True, exist_ok=True)
        try:
            self._write_mod_manifest(project_root, "base", [])
            self._write_mod_manifest(project_root, "expansion", ["base"])
            (project_root / "mods.json").write_text(
                '{\n  "active_mods": ["expansion"]\n}\n',
                encoding="utf-8",
            )

            self._write_tsv(
                project_root / "modules" / "base" / "data" / "regions" / "regions.tsv",
                ["hex", "center_x", "center_y"],
                [["AA0000", "10", "20"]],
            )
            self._write_tsv(
                project_root / "modules" / "base" / "data" / "regions" / "regions_pop.tsv",
                ["hex", "population"],
                [["AA0000", "1000"]],
            )
            self._write_tsv(
                project_root / "modules" / "expansion" / "data" / "regions" / "regions_pop.tsv",
                ["hex", "population"],
                [["AA0000", "1500"]],
            )

            self._write_tsv(
                project_root / "modules" / "base" / "data" / "countries" / "countries.tsv",
                ["id", "name"],
                [["USA", "United States"], ["CAN", "Canada"]],
            )
            self._write_tsv(
                project_root / "modules" / "expansion" / "data" / "countries" / "countries.tsv",
                ["id", "name"],
                [["USA", "United States of America"]],
            )
            self._write_tsv(
                project_root / "modules" / "base" / "data" / "countries" / "countries_eco.tsv",
                ["id", "gdp"],
                [["USA", "100"], ["CAN", "50"]],
            )
            self._write_tsv(
                project_root / "modules" / "expansion" / "data" / "countries" / "countries_eco.tsv",
                ["id", "gdp"],
                [["USA", "250"]],
            )

            (project_root / "modules" / "base" / "data" / "world").mkdir(parents=True, exist_ok=True)
            (project_root / "modules" / "expansion" / "data" / "world").mkdir(parents=True, exist_ok=True)
            (project_root / "modules" / "base" / "data" / "world" / "countries_treaties.toml").write_text(
                "\n".join(
                    [
                        "[countries_treaties.USA.GBR]",
                        'kind = "alliance"',
                        "trust = 40",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (project_root / "modules" / "expansion" / "data" / "world" / "countries_treaties.toml").write_text(
                "\n".join(
                    [
                        "[countries_treaties.USA.GBR]",
                        "trust = 90",
                        "",
                        "[countries_treaties.USA.FRA]",
                        'kind = "trade"',
                        "trust = 70",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            config = GameConfig(project_root)
            state = DataLoader(config).load_initial_state()

            self.assertEqual(config.active_mods, ["base", "expansion"])

            regions = state.get_table("regions")
            region_row = regions.to_dicts()[0]
            self.assertEqual(region_row["population"], 1500)

            countries = state.get_table("countries")
            self.assertEqual(len(countries), 2)
            usa_row = countries.filter(pl.col("id") == "USA").to_dicts()[0]
            can_row = countries.filter(pl.col("id") == "CAN").to_dicts()[0]
            self.assertEqual(usa_row["name"], "United States of America")
            self.assertEqual(usa_row["gdp"], 250)
            self.assertEqual(can_row["name"], "Canada")
            self.assertEqual(can_row["gdp"], 50)

            treaties = state.get_table("countries_treaties")
            treaty_rows = {(row["source"], row["target"]): row for row in treaties.to_dicts()}
            self.assertEqual(treaty_rows[("USA", "GBR")]["kind"], "alliance")
            self.assertEqual(treaty_rows[("USA", "GBR")]["trust"], 90)
            self.assertEqual(treaty_rows[("USA", "FRA")]["kind"], "trade")
            self.assertEqual(treaty_rows[("USA", "FRA")]["trust"], 70)
        finally:
            shutil.rmtree(project_root, ignore_errors=True)

    def _write_mod_manifest(self, project_root: Path, mod_id: str, dependencies: list[str]) -> None:
        mod_root = project_root / "modules" / mod_id
        (mod_root / "data").mkdir(parents=True, exist_ok=True)
        dependencies_literal = ", ".join(f'"{dependency}"' for dependency in dependencies)
        (mod_root / "mod.toml").write_text(
            "\n".join(
                [
                    f'id = "{mod_id}"',
                    f'name = "{mod_id}"',
                    'version = "0.0.1"',
                    f"dependencies = [{dependencies_literal}]",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _write_tsv(self, path: Path, headers: list[str], rows: list[list[str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["\t".join(headers)]
        lines.extend("\t".join(row) for row in rows)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
