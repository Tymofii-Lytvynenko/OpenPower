from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import polars as pl
import pytest
from PIL import Image
from polars.testing import assert_frame_equal

from src.server.io.data_load_manager import DataLoader
from src.shared.state import GameState


def _loader(
    project_root: Path,
    *data_dirs: Path,
    asset_path: Path | None = None,
) -> DataLoader:
    config = SimpleNamespace(
        project_root=project_root,
        get_data_dirs=lambda: list(data_dirs),
        get_asset_path=lambda _asset: asset_path or project_root / "missing.png",
    )
    return DataLoader(config)


def _write_tsv(path: Path, frame: pl.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_csv(path, separator="\t")


def test_load_save_uses_recovery_backup_and_reports_missing_slots(tmp_path: Path) -> None:
    save_root = tmp_path / "user_data" / "saves"
    save_root.mkdir(parents=True)
    loader = _loader(tmp_path)
    loader.migrations = Mock()

    for name, create_primary in (("backup-only", False), ("interrupted", True)):
        backup_dir = save_root / f".{name}.backup"
        backup_dir.mkdir()
        (backup_dir / "meta.json").write_text("{}", encoding="utf-8")
        if create_primary:
            (save_root / name).mkdir()

        state = loader.load_save(name)

        assert isinstance(state, GameState)
        assert state.globals["tick"] == 0

    with pytest.raises(FileNotFoundError, match="Save 'missing' not found"):
        loader.load_save("missing")


def test_load_save_restores_table_parquet_and_metadata(tmp_path: Path) -> None:
    save_dir = tmp_path / "user_data" / "saves" / "with-data"
    tables_dir = save_dir / "tables"
    tables_dir.mkdir(parents=True)
    (save_dir / "meta.json").write_text('{"globals":{"tick":42}}', encoding="utf-8")
    expected = pl.DataFrame({"id": ["AAA"]})
    expected.write_parquet(tables_dir / "countries.parquet")
    loader = _loader(tmp_path)
    loader.migrations = Mock()

    state = loader.load_save("with-data")

    assert state.globals["tick"] == 42
    assert_frame_equal(state.get_table("countries"), expected)


def test_load_save_reads_and_defaults_top_level_dataframes(tmp_path: Path) -> None:
    @dataclass
    class FrameState:
        snapshot: pl.DataFrame
        globals: dict[str, object] = field(default_factory=lambda: {"tick": 0})

    save_dir = tmp_path / "user_data" / "saves" / "frame-save"
    save_dir.mkdir(parents=True)
    snapshot_path = save_dir / "snapshot.parquet"
    snapshot_path.write_bytes(b"parquet placeholder")
    expected = pl.DataFrame({"value": [7]})
    loader = _loader(tmp_path)
    loader.migrations = Mock()

    with (
        patch("src.server.io.data_load_manager.GameState", FrameState),
        patch("src.server.io.data_load_manager.persistent_state_fields", return_value=fields(FrameState)),
        patch("src.server.io.data_load_manager.get_type_hints", return_value={"snapshot": pl.DataFrame}),
        patch("src.server.io.data_load_manager.pl.read_parquet", return_value=expected) as read_parquet,
    ):
        loaded = loader.load_save("frame-save")
        assert_frame_equal(loaded.snapshot, expected)
        read_parquet.assert_called_once_with(snapshot_path)

        snapshot_path.unlink()
        loaded_without_snapshot = loader.load_save("frame-save")

    assert loaded_without_snapshot.snapshot.is_empty()


def test_load_initial_state_keeps_empty_regions_explicit(tmp_path: Path) -> None:
    class EmptyStaticAssets:
        def load_definitions(self) -> dict[str, pl.DataFrame]:
            return {}

        def load_country_identity_distribution(self, _countries: pl.DataFrame) -> pl.DataFrame:
            return pl.DataFrame()

    loader = _loader(tmp_path)
    empty = pl.DataFrame()
    with (
        patch("src.server.io.data_load_manager.StaticAssetLoader", return_value=EmptyStaticAssets()),
        patch.object(loader, "_load_master_regions", return_value=empty),
        patch.object(loader, "_load_countries", return_value=empty),
        patch.object(loader, "_load_world_tables", return_value={}),
        patch.object(loader, "_load_domestic_production", return_value=empty),
    ):
        state = loader.load_initial_state()

    assert state.get_table("regions").is_empty()
    assert state.get_table("regional_production").is_empty()


def test_schema_registry_validation_errors_include_table_and_code(tmp_path: Path) -> None:
    registry = Mock()
    registry.validate_state.return_value = [SimpleNamespace(table="regions", code="missing_id")]
    loader = DataLoader(SimpleNamespace(project_root=tmp_path), schema_registry=registry)

    with pytest.raises(RuntimeError, match="regions:missing_id"):
        loader._apply_schema_registry(GameState())


def test_region_extensions_skip_missing_hex_and_key_only_files(tmp_path: Path) -> None:
    regions_dir = tmp_path / "regions"
    _write_tsv(regions_dir / "ignored.tsv", pl.DataFrame({"name": ["no hex"]}))
    _write_tsv(regions_dir / "keys.tsv", pl.DataFrame({"hex": ["AA0000"]}))
    _write_tsv(
        regions_dir / "labels.tsv",
        pl.DataFrame({"hex": ["AA0000"], "label": ["Capital"]}),
    )
    loader = _loader(tmp_path, tmp_path)

    enriched = loader._enrich_regions_data(pl.DataFrame({"hex": ["#AA0000"]}))

    assert enriched["label"].to_list() == ["Capital"]
    missing_regions_dir = _loader(tmp_path, tmp_path / "mod-without-regions")
    assert missing_regions_dir._enrich_regions_data(pl.DataFrame({"hex": ["#AA0000"]}))["hex"].to_list() == [
        "#AA0000"
    ]


def test_country_loading_skips_missing_directories_and_invalid_extensions(tmp_path: Path) -> None:
    first = tmp_path / "base" / "data"
    second = tmp_path / "empty-mod" / "data"
    countries_dir = first / "countries"
    _write_tsv(
        countries_dir / "countries.tsv",
        pl.DataFrame({"id": ["AAA"], "name": ["A Country"]}),
    )
    _write_tsv(countries_dir / "countries_invalid.tsv", pl.DataFrame({"name": ["ignored"]}))
    _write_tsv(countries_dir / "countries_keys.tsv", pl.DataFrame({"id": ["AAA"]}))
    loader = _loader(tmp_path, first, second)

    countries = loader._load_countries(pl.DataFrame())

    assert countries.select("id", "name").to_dicts() == [{"id": "AAA", "name": "A Country"}]


def test_region_dimensions_use_fallback_image_and_geo_columns_guard_inputs(tmp_path: Path) -> None:
    image_path = tmp_path / "assets" / "regions.png"
    image_path.parent.mkdir()
    Image.new("RGB", (8, 6)).save(image_path)
    loader = _loader(tmp_path, tmp_path, asset_path=image_path)

    assert loader._get_region_map_dimensions(pl.DataFrame({"center_x": [1], "center_y": [2]})) == (8, 6)
    module_data = tmp_path / "mod" / "data"
    module_image = module_data / "regions" / "regions.png"
    module_image.parent.mkdir(parents=True)
    Image.new("RGB", (4, 3)).save(module_image)
    module_loader = _loader(tmp_path, module_data, asset_path=image_path)
    assert module_loader._get_region_map_dimensions(
        pl.DataFrame({"center_x": [1], "center_y": [2]})
    ) == (4, 3)
    assert loader._add_region_geo_columns(pl.DataFrame()).is_empty()
    no_coordinates = loader._add_region_geo_columns(pl.DataFrame({"id": [1]}))
    assert "latitude" not in no_coordinates.columns


def test_world_parquet_files_are_loaded(tmp_path: Path) -> None:
    world_dir = tmp_path / "world"
    world_dir.mkdir()
    expected = pl.DataFrame({"source": ["AAA"], "target": ["BBB"], "value": [12]})
    expected.write_parquet(world_dir / "relations.parquet")

    tables = _loader(tmp_path, tmp_path)._load_world_tables()

    assert_frame_equal(tables["relations"], expected)


def test_world_merge_helpers_handle_empty_single_and_unkeyed_layers(tmp_path: Path) -> None:
    loader = _loader(tmp_path)
    one = pl.DataFrame({"id": ["AAA"], "name": ["A"]})
    unkeyed = loader._merge_world_layers(
        [pl.DataFrame({"left": [1]}), pl.DataFrame({"right": [2]})]
    )

    assert loader._merge_world_layers([]).is_empty()
    assert_frame_equal(loader._merge_world_layers([one]), one)
    assert unkeyed.to_dicts() == [{"left": 1, "right": None}, {"left": None, "right": 2}]
    assert loader._infer_merge_keys([one, pl.DataFrame({"id": ["BBB"], "name": ["B"]})]) == ["id"]
    assert loader._infer_merge_keys([pl.DataFrame({"left": [1]}), pl.DataFrame({"right": [2]})]) == []


def test_key_only_layered_records_are_deduplicated(tmp_path: Path) -> None:
    loader = _loader(tmp_path)

    merged = loader._merge_layered_records(
        [pl.DataFrame({"id": ["AAA"]}), pl.DataFrame({"id": ["AAA", "BBB"]})],
        keys=["id"],
    )

    assert merged["id"].to_list() == ["AAA", "BBB"]


def test_world_toml_shapes_and_invalid_roots(tmp_path: Path) -> None:
    loader = _loader(tmp_path)
    empty_path = tmp_path / "empty.toml"
    empty_path.write_text("", encoding="utf-8")
    fallback_path = tmp_path / "relations.toml"
    fallback_path.write_text("[other.AAA]\nBBB = 12\n", encoding="utf-8")
    list_path = tmp_path / "relations_list.toml"
    list_path.write_text(
        '[[relations_list]]\nsource = "AAA"\ntarget = "BBB"\nvalue = 9\n',
        encoding="utf-8",
    )
    multi_root_path = tmp_path / "relations_multiple.toml"
    multi_root_path.write_text("[first]\na = 1\n[second]\nb = 2\n", encoding="utf-8")
    scalar_path = tmp_path / "scalar.toml"
    scalar_path.write_text("scalar = 42\n", encoding="utf-8")

    assert loader._load_world_toml(empty_path).is_empty()
    assert loader._load_world_toml(fallback_path).to_dicts() == [
        {"source": "AAA", "target": "BBB", "value": 12}
    ]
    assert loader._load_world_toml(list_path).to_dicts() == [
        {"source": "AAA", "target": "BBB", "value": 9}
    ]
    with pytest.raises(RuntimeError, match="has no 'relations_multiple' root table"):
        loader._load_world_toml(multi_root_path)
    assert loader._load_world_toml(scalar_path).is_empty()


def test_world_matrix_ignores_non_mapping_targets(tmp_path: Path) -> None:
    rows = _loader(tmp_path)._flatten_world_matrix(
        {"AAA": "invalid", "BBB": {"CCC": {"trust": 50}, "DDD": 7}}
    )

    assert rows.to_dicts() == [
        {"source": "BBB", "target": "CCC", "trust": 50, "value": None},
        {"source": "BBB", "target": "DDD", "trust": None, "value": 7},
    ]


def test_domestic_production_accepts_scalars_and_wraps_invalid_data(tmp_path: Path) -> None:
    resources_dir = tmp_path / "countries" / "countries_res"
    resources_dir.mkdir(parents=True)
    (resources_dir / "AAA.toml").write_text("[resources]\ngrain = 12\n", encoding="utf-8")
    loader = _loader(tmp_path, tmp_path)

    rows = loader._load_domestic_production().to_dicts()
    assert rows == [
        {
            "country_id": "AAA",
            "game_resource_id": "grain",
            "domestic_production": 12.0,
            "is_legal": True,
            "is_gov_controlled": False,
            "tax_rate": 0.0,
        }
    ]

    (resources_dir / "AAA.toml").write_text('[resources]\ngrain = "invalid"\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="Failed to parse required country resource TOML"):
        loader._load_domestic_production()


def test_regional_production_accepts_list_entries_and_scalar_values(tmp_path: Path) -> None:
    resources_dir = tmp_path / "countries" / "countries_res"
    resources_dir.mkdir(parents=True)
    resource_file = resources_dir / "AAA.toml"
    resource_file.write_text("", encoding="utf-8")
    loader = _loader(tmp_path, tmp_path)
    loader._read_required_toml = lambda _path, _kind: {
        "regional_resources": [
            {"region_id": "#AA0000", "resources": {"grain": 3.5}},
        ]
    }

    regional = loader._load_regional_production(
        pl.DataFrame({"id": [1], "hex": ["AA0000"]})
    )

    assert regional.to_dicts() == [
        {
            "id": "AAA:1:grain",
            "country_id": "AAA",
            "region_id": 1,
            "game_resource_id": "grain",
            "domestic_production": 3.5,
        }
    ]
    assert loader._load_regional_production(pl.DataFrame()).is_empty()


@pytest.mark.parametrize(
    ("regional_resources", "message"),
    [
        ([1], "Each regional_resources list entry must be a mapping"),
        ([{"resources": {}}], "require a region identifier"),
        ([{"region": "AA", "resources": []}], "require a region identifier"),
        ("invalid", "must be a mapping or a list"),
        ({"AA": 1}, "entry 'AA' must be a mapping"),
    ],
)
def test_regional_resource_entry_shapes_are_validated(
    tmp_path: Path,
    regional_resources: object,
    message: str,
) -> None:
    loader = _loader(tmp_path)

    with pytest.raises(ValueError, match=message):
        loader._regional_resource_entries(regional_resources)


@pytest.mark.parametrize(
    ("value", "message"),
    [(None, "invalid"), (-1, "invalid"), (float("nan"), "invalid"), (float("inf"), "invalid")],
)
def test_regional_production_values_must_be_finite_and_nonnegative(
    tmp_path: Path,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _loader(tmp_path)._validated_nonnegative(value, "invalid regional production")


@pytest.mark.parametrize(
    "entries",
    [
        [("UNKNOWN", {"grain": 1})],
        [("AA0000", {"": 1})],
        [("AA0000", {"grain": {"production": 1, "tax_rate": 0.2}})],
    ],
)
def test_regional_production_rejects_unknown_regions_empty_ids_and_extra_fields(
    tmp_path: Path,
    entries: list[tuple[str, dict[str, object]]],
) -> None:
    resources_dir = tmp_path / "countries" / "countries_res"
    resources_dir.mkdir(parents=True)
    resource_file = resources_dir / "AAA.toml"
    resource_file.write_text("", encoding="utf-8")
    loader = _loader(tmp_path, tmp_path)
    loader._read_required_toml = lambda _path, _kind: {"regional_resources": {}}
    loader._regional_resource_entries = lambda _value: entries

    with pytest.raises(ValueError):
        loader._load_regional_production(pl.DataFrame({"id": [1], "hex": ["AA0000"]}))
