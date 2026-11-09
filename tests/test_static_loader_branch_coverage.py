from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from PIL import Image

from src.server.io import static_loader as static_loader_module
from src.server.io.static_loader import StaticAssetLoader


class StubConfig:
    def __init__(self, data_dirs=(), asset_root=None):
        self.data_dirs = list(data_dirs)
        self.asset_root = Path(asset_root or ".")

    def get_data_dirs(self):
        return self.data_dirs

    def get_asset_path(self, relative_path):
        return self.asset_root / relative_path


class FakeGameState:
    def __init__(self):
        self.tables = {}

    def update_table(self, name, value):
        self.tables[name] = value

    def get_table(self, name):
        return self.tables[name]


def write_tsv(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_compile_initial_state_loads_definitions_entities_and_world_tables(monkeypatch):
    monkeypatch.setattr(static_loader_module, "GameState", FakeGameState)
    loader = StaticAssetLoader(StubConfig())
    regions = pl.DataFrame({"id": [1]})
    countries = pl.DataFrame({"id": ["AAA"]})
    identities = pl.DataFrame({"country_id": ["AAA"]})
    calls = []

    def load_collection(folder):
        calls.append(folder)
        return {
            "definitions": {"resources": pl.DataFrame({"id": ["grain"]})},
            "world": {"wars": pl.DataFrame({"id": [2]})},
        }.get(folder, {})

    loader._load_toml_collection = load_collection
    loader._load_regions = lambda: regions
    loader._load_countries = lambda: countries
    loader.load_country_identity_distribution = lambda frame: identities if frame is countries else None

    state = loader.compile_initial_state()

    assert calls == ["definitions", "world"]
    assert set(state.tables) == {
        "def_resources", "regions", "countries", "country_identity_distribution", "wars"
    }
    assert state.tables["def_resources"].to_dicts() == [{"id": "grain"}]
    assert state.tables["regions"] is regions
    assert state.tables["countries"] is countries
    assert state.tables["country_identity_distribution"] is identities
    assert state.tables["wars"].to_dicts() == [{"id": 2}]
    assert loader.load_definitions()["resources"].to_dicts() == [{"id": "grain"}]


def test_load_regions_uses_new_path_then_legacy_path_and_calculates_geo_columns(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    write_tsv(first / "regions/regions.tsv", "hex\tcenter_x\tcenter_y\n#010203\t5\t10\n#040506\t2\t4\n")
    write_tsv(first / "map/regions.tsv", "hex\tcenter_x\tcenter_y\n#FFFFFF\t1\t1\n")
    write_tsv(second / "map/regions.tsv", "hex\tcenter_x\tcenter_y\n#010203\t8\t6\n070809\t2\t8\n")
    loader = StaticAssetLoader(StubConfig([first, second], asset_root=tmp_path / "assets"))

    regions = loader._load_regions()
    rows = {row["hex"]: row for row in regions.to_dicts()}

    assert set(rows) == {"#010203", "#040506", "#070809"}
    assert rows["#010203"]["center_x"] == 8
    assert rows["#010203"]["id"] == 0x010203
    assert rows["#010203"]["latitude"] == 90.0 - (6 / 9) * 180.0
    assert rows["#010203"]["longitude"] == (8 / 9) * 360.0 - 180.0


def test_load_regions_returns_empty_table_when_no_definitions_exist(tmp_path, capsys):
    loader = StaticAssetLoader(StubConfig([tmp_path]))

    assert loader._load_regions().is_empty()
    assert "No region definitions" in capsys.readouterr().out


def test_load_countries_handles_empty_master_and_merges_extensions(tmp_path):
    empty_loader = StaticAssetLoader(StubConfig([tmp_path / "empty"]))
    assert empty_loader._load_countries().is_empty()

    base, extension = tmp_path / "base", tmp_path / "extension"
    write_tsv(base / "countries/countries.tsv", "id\tname\tweight\nAAA\tAlpha\t1.5\nBBB\tBeta\t\n")
    write_tsv(base / "countries/countries_stats.tsv", "id\tpopulation\nAAA\t100\nBBB\t\n")
    write_tsv(base / "countries/countries_no_id.tsv", "label\tignored\nAlpha\t9\n")
    write_tsv(extension / "countries/countries_no_id.tsv", "label\tignored\nBeta\t9\n")
    regions = StaticAssetLoader(StubConfig([base, extension]))._load_countries()

    rows = {row["id"]: row for row in regions.to_dicts()}
    assert rows["AAA"]["name"] == "Alpha"
    assert rows["AAA"]["population"] == 100
    assert rows["BBB"]["population"] == 0
    assert rows["BBB"]["weight"] == 0
    assert "label" not in regions.columns


def test_identity_distribution_filters_invalid_values_and_applies_mod_precedence(tmp_path):
    base, expansion = tmp_path / "base", tmp_path / "expansion"
    write_tsv(
        base / "countries/country_languages.toml",
        """
[country_languages.USA]
English = 60
"English!" = 10
Other = 20
Zero = 0
Negative = -2
Invalid = "not-a-number"
NotFinite = nan
"漢字" = 5
"" = 100

[country_languages.CAN]
French = 100

[country_languages.HUGE]
First = 1e308
Second = 1e308

[country_languages.UNKNOWN]
Alien = 100
""",
    )
    write_tsv(base / "countries/country_religions.toml", "country_religions = \"not a table\"\n")
    write_tsv(
        expansion / "countries/country_languages.toml",
        "[country_languages.usa]\nSpanish = 90\nOther = 10\n",
    )
    loader = StaticAssetLoader(StubConfig([base, expansion]))

    table = loader.load_country_identity_distribution(pl.DataFrame({"id": ["usa", "CAN", "HUGE"]}))
    usa = table.filter(pl.col("country_id") == "USA").sort("identity_id").to_dicts()

    assert {row["identity_id"] for row in usa} == {"other", "spanish"}
    assert {row["population_share"] for row in usa} == {10.0, 90.0}
    assert all(row["source_year"] == 0 for row in usa)
    assert table.filter(pl.col("country_id") == "CAN")["identity_id"].to_list() == ["french"]
    assert not table.filter(pl.col("country_id") == "HUGE").height
    assert StaticAssetLoader._is_identity_other_bucket("other")
    assert not StaticAssetLoader._is_identity_other_bucket("english")


@pytest.mark.parametrize(
    "countries",
    [pl.DataFrame(), pl.DataFrame({"name": ["No ID"]})],
)
def test_identity_distribution_returns_typed_empty_table_for_invalid_country_input(tmp_path, countries):
    table = StaticAssetLoader(StubConfig([tmp_path])).load_country_identity_distribution(countries)

    assert table.is_empty()
    assert table.schema["is_other_bucket"] == pl.Boolean


def test_identity_distribution_ignores_non_table_profiles_and_non_dict_country_values(tmp_path):
    directory = tmp_path / "countries"
    directory.mkdir(parents=True)
    (directory / "country_languages.toml").write_text(
        'country_languages = "invalid profile collection"\n', encoding="utf-8"
    )
    (directory / "country_religions.toml").write_text(
        'country_religions.USA = "invalid country profile"\n', encoding="utf-8"
    )

    table = StaticAssetLoader(StubConfig([tmp_path])).load_country_identity_distribution(
        pl.DataFrame({"id": ["USA"]})
    )

    assert table.is_empty()


def test_identity_distribution_wraps_invalid_toml_with_source_path(tmp_path):
    path = tmp_path / "countries/country_languages.toml"
    write_tsv(path, "[country_languages.USA\n")

    with pytest.raises(RuntimeError, match="Failed to parse country identity data") as error:
        StaticAssetLoader(StubConfig([tmp_path])).load_country_identity_distribution(
            pl.DataFrame({"id": ["USA"]})
        )

    assert str(path) in str(error.value)


def test_identity_slug_normalizes_ascii_and_keeps_non_latin_labels_addressable():
    assert StaticAssetLoader._identity_slug("Beyoncé & Friends") == "beyonce_friends"
    assert StaticAssetLoader._identity_slug("漢字").startswith("group_")
    assert StaticAssetLoader._identity_slug("!!!").startswith("group_")


def test_read_tsv_filters_internal_columns_and_wraps_parse_errors(tmp_path, monkeypatch):
    path = tmp_path / "regions.tsv"
    write_tsv(path, "hex\tname\t_private\n00FF00\tGreen\tignored\n")
    loader = StaticAssetLoader(StubConfig())

    table = loader._read_tsv(path)
    assert table.columns == ["hex", "name"]
    assert table["hex"].to_list() == ["00FF00"]

    monkeypatch.setattr(static_loader_module.pl, "read_csv", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("broken")))
    with pytest.raises(RuntimeError, match="Failed to read required static TSV"):
        loader._read_tsv(path)


def test_runtime_ids_and_geo_columns_cover_empty_missing_and_dimension_fallbacks(tmp_path):
    loader = StaticAssetLoader(StubConfig([], asset_root=tmp_path))
    assert loader._add_region_geo_columns(pl.DataFrame()).is_empty()
    no_geo = pl.DataFrame({"id": [1]})
    assert loader._add_region_geo_columns(no_geo).columns == ["id"]

    with_coords = pl.DataFrame({"center_x": [0, 4], "center_y": [0, 2]})
    assert loader._get_region_map_dimensions(with_coords) == (5, 3)
    asset = tmp_path / "map/regions.png"
    asset.parent.mkdir(parents=True)
    Image.new("RGB", (9, 6)).save(asset)
    assert loader._get_region_map_dimensions(with_coords) == (9, 6)
    image = tmp_path / "regions/regions.png"
    image.parent.mkdir(parents=True)
    Image.new("RGB", (12, 8)).save(image)
    assert StaticAssetLoader(StubConfig([tmp_path], asset_root=tmp_path))._get_region_map_dimensions(with_coords) == (12, 8)


def test_load_toml_collection_skips_missing_folders_and_empty_tables(tmp_path):
    loader = StaticAssetLoader(StubConfig([tmp_path]))
    assert loader._load_toml_collection("missing")== {}
    (tmp_path / "world").mkdir()
    (tmp_path / "world/empty.toml").write_text("other = 1\n", encoding="utf-8")
    (tmp_path / "world/relations.toml").write_text("[relations.A.B]\ntrust = 4\n", encoding="utf-8")

    tables = loader._load_toml_collection("world")

    assert set(tables) == {"relations"}
    assert tables["relations"].to_dicts() == [{"source": "A", "target": "B", "trust": 4}]


def test_toml_parser_handles_missing_keys_unknown_values_and_empty_matrices(tmp_path, capsys):
    loader = StaticAssetLoader(StubConfig())
    missing = tmp_path / "missing.toml"
    missing.write_text("other = 1\n", encoding="utf-8")
    unknown = tmp_path / "unknown.toml"
    unknown.write_text("value = 7\n", encoding="utf-8")
    empty_matrix = tmp_path / "matrix.toml"
    empty_matrix.write_text("[matrix]\n", encoding="utf-8")

    assert loader._parse_toml_file(missing, "missing").is_empty()
    assert loader._parse_toml_file(unknown, "value").is_empty()
    assert "Unknown data structure" in capsys.readouterr().out
    assert loader._parse_toml_file(empty_matrix, "matrix").is_empty()


def test_flatten_helpers_skip_invalid_rows_and_handle_scalar_and_complex_values():
    loader = StaticAssetLoader(StubConfig())
    entities = loader._flatten_entity_dict({"one": {"name": "First"}, "invalid": [1, 2]})
    matrix = loader._flatten_matrix(
        {
            "A": {"B": 7, "C": {"trust": 5}},
            "invalid": "not a mapping",
        }
    )

    assert entities.to_dicts() == [{"id": "one", "name": "First"}]
    assert matrix.to_dicts() == [
        {"source": "A", "target": "B", "value": 7, "trust": None},
        {"source": "A", "target": "C", "value": None, "trust": 5},
    ]
    assert loader._flatten_matrix({"A": []}).is_empty()
