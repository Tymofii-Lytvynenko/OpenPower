import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import polars as pl

from src.server.io.data_load_manager import DataLoader
from src.server.io.static_loader import StaticAssetLoader
from src.shared.config import GameConfig


class TestDataLoaderModLayering(unittest.TestCase):
    def test_single_extension_layer_merges_duplicate_keys_without_multiplying_regions(self):
        loader = DataLoader(GameConfig(Path(__file__).resolve().parent.parent))
        extension = pl.DataFrame({"hex": ["#010203", "#010203"], "population": [10, 20], "label": ["Region", None]})
        merged = loader._merge_layered_records([extension], keys=["hex"])
        self.assertEqual(merged.to_dicts(), [{"hex": "#010203", "population": 20, "label": "Region"}])

    def setUp(self):
        self.temp_root = Path(__file__).resolve().parent.parent / ".temp"
        self.temp_root.mkdir(exist_ok=True)

    def test_base_treaty_and_war_toml_files_load_into_expected_tables(self):
        project_root = Path(__file__).resolve().parent.parent
        tables = StaticAssetLoader(GameConfig(project_root))._load_toml_collection("world")

        self.assertGreater(tables["countries_treaties"].height, 0)
        self.assertEqual(tables["countries_wars"].height, 8)
        self.assertTrue({"side_a", "side_b"}.issubset(tables["countries_wars"].columns))

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
            (project_root / "modules/base/data/countries/country_languages.toml").write_text(
                '[country_languages.USA]\nEnglish = 60\nSpanish = 20\n'
                '[country_languages.CAN]\nEnglish = 50\nFrench = 50\n'
                '[country_languages.UNKNOWN]\nUnknown = 100\n', encoding="utf-8",
            )
            (project_root / "modules/expansion/data/countries/country_languages.toml").write_text(
                '[country_languages.USA]\nEnglish = 90\nSpanish = 10\n', encoding="utf-8",
            )
            (project_root / "modules/base/data/countries/country_religions.toml").write_text(
                '[country_religions.USA]\nChristian = 60\nOther = 40\n', encoding="utf-8",
            )
            state = DataLoader(config).load_initial_state()

            identities = state.get_table("country_identity_distribution")
            self.assertEqual(identities.height, 6)
            self.assertEqual(set(identities["country_id"].to_list()), {"USA", "CAN"})
            english = identities.filter(
                (pl.col("country_id") == "USA") & (pl.col("identity_id") == "english")
            )
            self.assertEqual(english.item(0, "population_share"), 90)
            self.assertEqual(english.item(0, "source_year"), 0)
            self.assertEqual(identities.filter(pl.col("identity_type") == "religion")["population_share"].sum(), 100)

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

    def test_production_loader_loads_definitions_before_entities_and_world_relations(self):
        project_root = self.temp_root / f"definitions-order-{uuid4().hex}"
        project_root.mkdir(parents=True, exist_ok=True)
        try:
            self._write_mod_manifest(project_root, "base", [])
            (project_root / "mods.json").write_text(
                '{"active_mods": ["base"]}\n',
                encoding="utf-8",
            )
            (project_root / "modules" / "base" / "data" / "definitions" / "resources.toml").parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            (project_root / "modules" / "base" / "data" / "definitions" / "resources.toml").write_text(
                "[[resources]]\nid = \"grain\"\nname = \"Grain\"\n",
                encoding="utf-8",
            )
            self._write_tsv(
                project_root / "modules" / "base" / "data" / "regions" / "regions.tsv",
                ["hex", "center_x", "center_y"],
                [["AA0000", "10", "20"]],
            )
            self._write_tsv(
                project_root / "modules" / "base" / "data" / "countries" / "countries.tsv",
                ["id", "name"],
                [["AAA", "A Country"]],
            )
            world_file = project_root / "modules" / "base" / "data" / "world" / "countries_relations.toml"
            world_file.parent.mkdir(parents=True, exist_ok=True)
            world_file.write_text(
                "[countries_relations.AAA.BBB]\nvalue = 50\n",
                encoding="utf-8",
            )

            config = GameConfig(project_root)
            loader = DataLoader(config)
            load_order = []

            def record(name, operation):
                def wrapped(*args, **kwargs):
                    load_order.append(name)
                    return operation(*args, **kwargs)
                return wrapped

            loader._load_master_regions = record("regions", loader._load_master_regions)
            loader._load_countries = record("countries", loader._load_countries)
            loader._load_world_tables = record("world", loader._load_world_tables)
            original_collection = StaticAssetLoader._load_toml_collection

            def record_definitions(static_loader, folder_name):
                if folder_name == "definitions":
                    load_order.append("definitions")
                return original_collection(static_loader, folder_name)

            with patch.object(
                StaticAssetLoader,
                "_load_toml_collection",
                autospec=True,
                side_effect=record_definitions,
            ):
                state = loader.load_initial_state()

            self.assertEqual(load_order, ["definitions", "regions", "countries", "world"])
            self.assertEqual(state.get_table("def_resources")["id"].to_list(), ["grain"])
            self.assertEqual(state.get_table("regions")["id"].to_list(), [0xAA0000])
            self.assertEqual(state.get_table("countries")["id"].to_list(), ["AAA"])
            self.assertEqual(state.get_table("countries_relations")["value"].to_list(), [50])
        finally:
            shutil.rmtree(project_root, ignore_errors=True)

    def test_region_hex_input_is_normalized_and_packed_from_bgr(self):
        project_root = self.temp_root / f"hex-normalization-{uuid4().hex}"
        project_root.mkdir(parents=True, exist_ok=True)
        try:
            self._write_mod_manifest(project_root, "base", [])
            (project_root / "mods.json").write_text(
                '{"active_mods": ["base"]}\n',
                encoding="utf-8",
            )
            self._write_tsv(
                project_root / "modules" / "base" / "data" / "regions" / "regions.tsv",
                ["hex", "center_x", "center_y"],
                [["ff8000", "10", "20"], ["#00aaff", "30", "40"]],
            )

            regions = DataLoader(GameConfig(project_root)).load_initial_state().get_table("regions")

            rows_by_hex = {row["hex"]: row for row in regions.to_dicts()}
            self.assertEqual(rows_by_hex["#FF8000"]["id"], 0xFF8000)
            self.assertEqual(rows_by_hex["#00AAFF"]["id"], 0x00AAFF)
        finally:
            shutil.rmtree(project_root, ignore_errors=True)

    def test_static_toml_parser_supports_list_entity_and_matrix_shapes(self):
        project_root = self.temp_root / f"toml-shapes-{uuid4().hex}"
        project_root.mkdir(parents=True, exist_ok=True)
        try:
            loader = StaticAssetLoader(GameConfig(project_root))
            definitions = project_root / "resources.toml"
            definitions.write_text(
                "[[resources]]\nid = \"grain\"\nproduction = 7\n",
                encoding="utf-8",
            )
            entities = project_root / "unit_types.toml"
            entities.write_text(
                "[unit_types.infantry]\nname = \"Infantry\"\nattack = 4\n",
                encoding="utf-8",
            )
            relations = project_root / "countries_relations.toml"
            relations.write_text(
                "[countries_relations.AAA.BBB]\ntrust = 50\n",
                encoding="utf-8",
            )

            list_table = loader._parse_toml_file(definitions, "resources")
            entity_table = loader._parse_toml_file(entities, "unit_types")
            relation_table = loader._parse_toml_file(relations, "countries_relations")

            self.assertEqual(list_table["id"].to_list(), ["grain"])
            self.assertEqual(entity_table["id"].to_list(), ["infantry"])
            self.assertEqual(entity_table["attack"].to_list(), [4])
            relation = relation_table.to_dicts()[0]
            self.assertEqual((relation["source"], relation["target"], relation["trust"]), ("AAA", "BBB", 50))
        finally:
            shutil.rmtree(project_root, ignore_errors=True)

    def test_required_static_parse_errors_include_the_source_path(self):
        project_root = self.temp_root / f"invalid-assets-{uuid4().hex}"
        project_root.mkdir(parents=True, exist_ok=True)
        try:
            tsv_path = project_root / "regions.tsv"
            tsv_path.write_text("hex\nAA0000\n", encoding="utf-8")
            toml_path = project_root / "resources.toml"
            toml_path.write_text("[resources]\n", encoding="utf-8")
            data_loader = DataLoader(GameConfig(project_root))
            static_loader = StaticAssetLoader(GameConfig(project_root))

            with patch("src.server.io.data_load_manager.pl.read_csv", side_effect=OSError("bad TSV")):
                with self.assertRaises(RuntimeError) as context:
                    data_loader._read_clean_tsv(tsv_path)
                self.assertIn(str(tsv_path), str(context.exception))
            with patch("src.server.io.static_loader.pl.read_csv", side_effect=OSError("bad TSV")):
                with self.assertRaises(RuntimeError) as context:
                    static_loader._read_tsv(tsv_path)
                self.assertIn(str(tsv_path), str(context.exception))
            with patch("src.server.io.data_load_manager.rtoml.load", side_effect=ValueError("bad TOML")):
                with self.assertRaises(RuntimeError) as context:
                    data_loader._load_world_toml(toml_path)
                self.assertIn(str(toml_path), str(context.exception))
            with patch("src.server.io.static_loader.rtoml.load", side_effect=ValueError("bad TOML")):
                with self.assertRaises(RuntimeError) as context:
                    static_loader._parse_toml_file(toml_path, "resources")
                self.assertIn(str(toml_path), str(context.exception))
        finally:
            shutil.rmtree(project_root, ignore_errors=True)

    def test_explicit_regional_resource_output_loads_without_apportioning_country_totals(self):
        project_root = self.temp_root / f"regional-resource-test-{uuid4().hex}"
        project_root.mkdir(parents=True, exist_ok=True)
        try:
            self._write_mod_manifest(project_root, "base", [])
            (project_root / "mods.json").write_text(
                '{"active_mods": ["base"]}\n',
                encoding="utf-8",
            )
            self._write_tsv(
                project_root / "modules" / "base" / "data" / "regions" / "regions.tsv",
                ["hex", "iso_region", "owner", "center_x", "center_y"],
                [["AA0000", "AA-X01", "AAA", "10", "20"]],
            )
            self._write_tsv(
                project_root / "modules" / "base" / "data" / "countries" / "countries.tsv",
                ["id", "un_member"],
                [["AAA", "true"]],
            )
            resource_path = (
                project_root
                / "modules"
                / "base"
                / "data"
                / "countries"
                / "countries_res"
                / "AAA.toml"
            )
            resource_path.parent.mkdir(parents=True, exist_ok=True)
            resource_path.write_text(
                "\n".join(
                    [
                        "[resources.cereals]",
                        "production = 100.0",
                        "",
                        '[regional_resources."AA-X01".cereals]',
                        "production = 40.0",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            state = DataLoader(GameConfig(project_root)).load_initial_state()

            regional = state.get_table("regional_production")
            self.assertEqual(regional.height, 1)
            self.assertEqual(regional["region_id"][0], state.get_table("regions")["id"][0])
            self.assertEqual(regional["country_id"][0], "AAA")
            self.assertEqual(regional["game_resource_id"][0], "cereals")
            self.assertEqual(regional["domestic_production"][0], 40.0)
            self.assertEqual(state.get_table("domestic_production")["domestic_production"][0], 100.0)
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
