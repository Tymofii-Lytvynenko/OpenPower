import dataclasses
import math
from pathlib import Path
from typing import Any, Dict, List, Sequence, get_type_hints

import orjson
import polars as pl
import rtoml
from PIL import Image

from src.core.region_adjacency_source import load_region_adjacency
from src.core.saves import save_backup_path, validate_save_name
from src.server.io.migrations import CORE_SAVE_MIGRATIONS
from src.server.io.static_loader import StaticAssetLoader
from src.shared.config import GameConfig
from src.shared.migrations import MigrationRegistry
from src.shared.schema import WorldSchemaRegistry
from src.shared.state import GameState, persistent_state_fields


class DataLoader:
    """
    Responsible for loading GameState data from two sources:
    1. Static Assets (TSV/TOML) -> For starting a fresh game (load_initial_state).
    2. User Saves (Parquet/JSON) -> For loading a saved session (load_save).
    """

    def __init__(
        self,
        config: GameConfig,
        migrations: MigrationRegistry | None = None,
        schema_registry: WorldSchemaRegistry | None = None,
    ):
        self.config = config
        self.save_root = config.project_root / "user_data" / "saves"
        self.migrations = migrations or MigrationRegistry(CORE_SAVE_MIGRATIONS)
        self.schema_registry = schema_registry

    # =========================================================================
    #  PART 1: SAVE GAME LOADING (Reflection Based)
    # =========================================================================

    def load_save(self, save_name: str) -> GameState:
        """
        Reconstructs a GameState from a save directory using type-driven reflection.
        """
        safe_name = validate_save_name(save_name)
        save_dir = self.save_root / safe_name
        backup_dir = save_backup_path(self.save_root, safe_name)
        if not save_dir.is_dir():
            if backup_dir.is_dir() and (backup_dir / "meta.json").exists():
                save_dir = backup_dir
            else:
                raise FileNotFoundError(f"Save '{safe_name}' not found.")
        elif not (save_dir / "meta.json").exists() and backup_dir.is_dir() and (backup_dir / "meta.json").exists():
            save_dir = backup_dir

        print(f"[DataLoader] Loading save '{safe_name}'...")

        meta_path = save_dir / "meta.json"
        if meta_path.exists():
            with open(meta_path, "rb") as f:
                meta_data = orjson.loads(f.read())
        else:
            print(f"[DataLoader] Warning: meta.json not found for {save_name}. Using defaults.")
            meta_data = {}

        loaded_tables = {}
        tables_dir = save_dir / "tables"
        if tables_dir.exists():
            for p_file in tables_dir.glob("*.parquet"):
                loaded_tables[p_file.stem] = pl.read_parquet(p_file)

        self.migrations.migrate(meta_data, loaded_tables)
        constructor_args = {}
        type_hints = get_type_hints(GameState)

        for field in persistent_state_fields():
            key = field.name
            target_type = type_hints.get(key)

            if key == "tables":
                constructor_args[key] = loaded_tables

            elif target_type == pl.DataFrame:
                p_file = save_dir / f"{key}.parquet"
                if p_file.exists():
                    constructor_args[key] = pl.read_parquet(p_file)
                else:
                    constructor_args[key] = pl.DataFrame()

            elif dataclasses.is_dataclass(target_type):
                data_dict = meta_data.get(key, {})
                constructor_args[key] = target_type(**data_dict)  # type: ignore[arg-type]

            else:
                if key in meta_data:
                    constructor_args[key] = meta_data[key]

        state = GameState(**constructor_args)
        self._apply_schema_registry(state)
        print(f"[DataLoader] Save loaded successfully. Tick: {state.globals.get('tick', 0)}")
        return state

    # =========================================================================
    #  PART 2: INITIAL STATE COMPILATION (Static Assets)
    # =========================================================================

    def load_initial_state(self) -> GameState:
        print("[DataLoader] Compiling state (Hex-Key Mode)...")
        state = GameState()

        static_assets = StaticAssetLoader(self.config)
        definitions = static_assets.load_definitions()
        for table_name, definition_df in definitions.items():
            state.update_table(f"def_{table_name}", definition_df)

        regions_df = self._load_master_regions()

        if not regions_df.is_empty():
            regions_df = self._generate_int_id(regions_df)
            regions_df = self._enrich_regions_data(regions_df)
            regions_df = self._add_region_geo_columns(regions_df)

            num_cols = [c for c, t in regions_df.schema.items() if t in (pl.Float64, pl.Int64, pl.Int32)]
            if num_cols:
                regions_df = regions_df.with_columns(pl.col(num_cols).fill_null(0))

            state.update_table("regions", regions_df)
            state.update_table("region_adjacency", load_region_adjacency(self.config, regions_df["id"].to_list()))
            print(f"[DataLoader] Regions loaded: {len(regions_df)}")
        else:
            print("[DataLoader] CRITICAL: No regions found!")
            state.update_table("regions", pl.DataFrame())

        countries_df = self._load_countries(regions_df)
        state.update_table("countries", countries_df if not countries_df.is_empty() else pl.DataFrame())
        # The production loader bypasses compile_initial_state; identity data must
        # enter this path before schema initialization and the bootstrap system.
        state.update_table(
            "country_identity_distribution",
            static_assets.load_country_identity_distribution(countries_df),
        )

        for table_name, world_df in self._load_world_tables().items():
            print(f"[DataLoader] Loading world table: {table_name}")
            state.update_table(table_name, world_df)

        prod_df = self._load_domestic_production()
        state.update_table("domestic_production", prod_df)
        regional_prod_df = self._load_regional_production(regions_df)
        state.update_table("regional_production", regional_prod_df)

        self._apply_schema_registry(state)
        return state

    def _apply_schema_registry(self, state: GameState) -> None:
        if self.schema_registry is None:
            return
        self.schema_registry.capture_state(state)
        self.schema_registry.ensure_state(state)
        issues = self.schema_registry.validate_state(state)
        if issues:
            details = "; ".join(f"{issue.table}:{issue.code}" for issue in issues)
            raise RuntimeError(f"World schema validation failed: {details}")

    def _read_clean_tsv(self, path: Path) -> pl.DataFrame:
        """Reads TSV, forcing 'hex' to string, and ignoring '_' columns."""
        try:
            df = pl.read_csv(
                path,
                separator="\t",
                ignore_errors=True,
                infer_schema_length=1000,
                schema_overrides={"hex": pl.String},
            )
            valid_cols = [c for c in df.columns if not c.startswith("_")]
            return df.select(valid_cols)
        except Exception as error:
            raise RuntimeError(f"Failed to read required static TSV: {path}") from error

    def _read_required_toml(self, path: Path, asset_kind: str) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as source_file:
                return rtoml.load(source_file)
        except Exception as error:
            raise RuntimeError(f"Failed to parse required {asset_kind} TOML: {path}") from error

    def _load_master_regions(self) -> pl.DataFrame:
        layers: List[pl.DataFrame] = []

        for data_dir in self.config.get_data_dirs():
            paths = [data_dir / "regions" / "regions.tsv", data_dir / "map" / "regions.tsv"]
            for p in paths:
                if p.exists():
                    df = self._read_clean_tsv(p)
                    if "hex" in df.columns:
                        df = df.with_columns(pl.col("hex").str.strip_prefix("#").str.to_uppercase())
                        layers.append(df)
                    break

        return self._merge_layered_records(layers, keys=["hex"])

    def _generate_int_id(self, df: pl.DataFrame) -> pl.DataFrame:
        df = df.with_columns([
            pl.col("hex").str.slice(0, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_r"),
            pl.col("hex").str.slice(2, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_g"),
            pl.col("hex").str.slice(4, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_b"),
        ])
        df = df.with_columns(
            (pl.col("_b") + (pl.col("_g") * 256) + (pl.col("_r") * 65536)).cast(pl.Int32).alias("id")
        )
        df = df.with_columns(("#" + pl.col("hex")).alias("hex"))
        return df.drop(["_r", "_g", "_b"])

    def _enrich_regions_data(self, main_df: pl.DataFrame) -> pl.DataFrame:
        layered_extensions: Dict[str, List[pl.DataFrame]] = {}

        for data_dir in self.config.get_data_dirs():
            target_dir = data_dir / "regions"
            if not target_dir.exists():
                continue

            for file_path in target_dir.glob("*.tsv"):
                if file_path.name == "regions.tsv":
                    continue

                aux_df = self._read_clean_tsv(file_path)
                if "hex" not in aux_df.columns:
                    continue

                aux_df = aux_df.with_columns(
                    pl.when(pl.col("hex").str.starts_with("#"))
                    .then(pl.col("hex"))
                    .otherwise("#" + pl.col("hex"))
                    .str.to_uppercase()
                    .alias("hex")
                )
                layered_extensions.setdefault(file_path.name, []).append(aux_df)

        for file_name in sorted(layered_extensions):
            merged_extension = self._merge_layered_records(layered_extensions[file_name], keys=["hex"])
            if merged_extension.is_empty() or merged_extension.columns == ["hex"]:
                continue

            print(f"[DataLoader] Merging data from: {file_name}")
            main_df = main_df.join(merged_extension, on="hex", how="left")

        return main_df

    def _load_countries(self, regions_df: pl.DataFrame) -> pl.DataFrame:
        print("[DataLoader] Loading Countries...")

        master_layers: List[pl.DataFrame] = []
        for data_dir in self.config.get_data_dirs():
            master_path = data_dir / "countries" / "countries.tsv"
            if master_path.exists():
                master_layers.append(self._read_clean_tsv(master_path))

        main_df = self._merge_layered_records(master_layers, keys=["id"])
        if main_df.is_empty():
            return pl.DataFrame()

        layered_extensions: Dict[str, List[pl.DataFrame]] = {}
        for data_dir in self.config.get_data_dirs():
            target_dir = data_dir / "countries"
            if not target_dir.exists():
                continue

            for file_path in target_dir.glob("countries_*.tsv"):
                aux_df = self._read_clean_tsv(file_path)
                if "id" not in aux_df.columns:
                    continue
                layered_extensions.setdefault(file_path.name, []).append(aux_df)

        for file_name in sorted(layered_extensions):
            merged_extension = self._merge_layered_records(layered_extensions[file_name], keys=["id"])
            if merged_extension.is_empty() or merged_extension.columns == ["id"]:
                continue

            print(f"[DataLoader] Merging country data: {file_name}")
            main_df = main_df.join(merged_extension, on="id", how="left")

        num_cols = [c for c, t in main_df.schema.items() if t in (pl.Float64, pl.Int64, pl.Int32)]
        if num_cols:
            main_df = main_df.with_columns(pl.col(num_cols).fill_null(0))

        print(f"[DataLoader] Countries loaded: {len(main_df)} rows.")
        return main_df

    def _add_region_geo_columns(self, regions_df: pl.DataFrame) -> pl.DataFrame:
        if regions_df.is_empty() or not {"center_x", "center_y"}.issubset(set(regions_df.columns)):
            return regions_df

        map_width, map_height = self._get_region_map_dimensions(regions_df)
        return regions_df.with_columns(
            (90.0 - (pl.col("center_y").cast(pl.Float64) / float(map_height)) * 180.0).alias("latitude"),
            ((pl.col("center_x").cast(pl.Float64) / float(map_width)) * 360.0 - 180.0).alias("longitude"),
        )

    def _get_region_map_dimensions(self, regions_df: pl.DataFrame) -> tuple[int, int]:
        for data_dir in self.config.get_data_dirs():
            candidate = data_dir / "regions" / "regions.png"
            if candidate.exists():
                return self._read_image_size(candidate)

        fallback = self.config.get_asset_path("map/regions.png")
        if fallback.exists():
            return self._read_image_size(fallback)

        max_x = int(regions_df["center_x"].max() or 1) + 1
        max_y = int(regions_df["center_y"].max() or 1) + 1
        return max_x, max_y

    def _read_image_size(self, path: Path) -> tuple[int, int]:
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(path) as image:
            return image.size

    def _load_world_tables(self) -> Dict[str, pl.DataFrame]:
        layered_tables: Dict[str, List[pl.DataFrame]] = {}

        for data_dir in self.config.get_data_dirs():
            world_dir = data_dir / "world"
            if not world_dir.exists():
                continue

            for p_file in world_dir.glob("*.parquet"):
                layered_tables.setdefault(p_file.stem, []).append(pl.read_parquet(p_file))

            for t_file in world_dir.glob("*.toml"):
                world_df = self._load_world_toml(t_file)
                if not world_df.is_empty():
                    layered_tables.setdefault(t_file.stem, []).append(world_df)

        merged_tables: Dict[str, pl.DataFrame] = {}
        for table_name in sorted(layered_tables):
            merged_tables[table_name] = self._merge_world_layers(layered_tables[table_name])

        return merged_tables

    def _merge_world_layers(self, layers: Sequence[pl.DataFrame]) -> pl.DataFrame:
        valid_layers = [df for df in layers if not df.is_empty()]
        if not valid_layers:
            return pl.DataFrame()
        if len(valid_layers) == 1:
            return valid_layers[0]

        merge_keys = self._infer_merge_keys(valid_layers)
        if merge_keys:
            return self._merge_layered_records(valid_layers, keys=merge_keys)

        return pl.concat(valid_layers, how="diagonal_relaxed")

    def _infer_merge_keys(self, layers: Sequence[pl.DataFrame]) -> List[str]:
        shared_columns = set(layers[0].columns)
        for df in layers[1:]:
            shared_columns &= set(df.columns)

        if {"source", "target"}.issubset(shared_columns):
            return ["source", "target"]
        if "id" in shared_columns:
            return ["id"]
        return []

    def _merge_layered_records(self, layers: Sequence[pl.DataFrame], keys: Sequence[str]) -> pl.DataFrame:
        valid_layers = [df for df in layers if not df.is_empty() and set(keys).issubset(df.columns)]
        if not valid_layers:
            return pl.DataFrame()
        if len(valid_layers) == 1 and not valid_layers[0].select(list(keys)).is_duplicated().any():
            return valid_layers[0]
        # Duplicate extension keys must not multiply master rows during joins.

        tagged_layers = [
            df.with_columns(pl.lit(priority).alias("__layer_priority"))
            for priority, df in enumerate(valid_layers)
        ]
        combined = pl.concat(tagged_layers, how="diagonal_relaxed")

        value_cols = [column for column in combined.columns if column not in {*keys, "__layer_priority"}]
        if not value_cols:
            return combined.select(list(keys)).unique(maintain_order=True)

        aggregated_columns = [
            pl.col(column).sort_by("__layer_priority").drop_nulls().last().alias(column)
            for column in value_cols
        ]
        return combined.group_by(list(keys), maintain_order=True).agg(aggregated_columns)

    def _load_world_toml(self, path: Path) -> pl.DataFrame:
        data = self._read_required_toml(path, "world")

        if not data:
            return pl.DataFrame()

        if path.stem in data:
            raw = data[path.stem]
        elif len(data) == 1:
            raw = next(iter(data.values()))
        else:
            raise RuntimeError(f"World TOML {path} has no '{path.stem}' root table.")

        if isinstance(raw, list):
            return pl.from_dicts(raw) if raw else pl.DataFrame()

        if isinstance(raw, dict):
            return self._flatten_world_matrix(raw)

        return pl.DataFrame()

    def _flatten_world_matrix(self, matrix: Dict[str, Any]) -> pl.DataFrame:
        rows = []
        for source, targets in matrix.items():
            if not isinstance(targets, dict):
                continue

            for target, value in targets.items():
                row = {
                    "source": source,
                    "target": target,
                }
                if isinstance(value, dict):
                    row.update(value)
                else:
                    row["value"] = value
                rows.append(row)

        return pl.from_dicts(rows) if rows else pl.DataFrame()

    def _load_domestic_production(self) -> pl.DataFrame:
        print("[DataLoader] Reading TOMLs for dynamic domestic production...")
        records = []
        for data_dir in self.config.get_data_dirs():
            target_dir = data_dir / "countries" / "countries_res"
            if not target_dir.exists():
                continue

            for file_path in target_dir.glob("*.toml"):
                country_id = file_path.stem
                try:
                    data = self._read_required_toml(file_path, "country resource")
                    if "resources" in data:
                        for res_id, res_data in data["resources"].items():
                            row = {
                                "country_id": country_id,
                                "game_resource_id": res_id,
                            }
                            if isinstance(res_data, dict):
                                row["domestic_production"] = float(res_data.get("production", 0))
                                row["is_legal"] = bool(res_data.get("is_legal", True))
                                row["is_gov_controlled"] = bool(res_data.get("is_gov_controlled", False))
                                row["tax_rate"] = float(res_data.get("tax_rate", 0.0))
                            else:
                                row["domestic_production"] = float(res_data)
                                row["is_legal"] = True
                                row["is_gov_controlled"] = False
                                row["tax_rate"] = 0.0

                            records.append(row)
                except Exception as error:
                    raise RuntimeError(f"Failed to parse required country resource TOML: {file_path}") from error

        if records:
            return pl.DataFrame(records)
        return pl.DataFrame(
            {"country_id": [], "game_resource_id": [], "domestic_production": []},
            schema={"country_id": pl.Utf8, "game_resource_id": pl.Utf8, "domestic_production": pl.Float64},
        )

    def _load_regional_production(self, regions: pl.DataFrame) -> pl.DataFrame:
        """Load only explicit region/resource entries; national totals are never apportioned."""

        schema = {
            "id": pl.Utf8,
            "country_id": pl.Utf8,
            "region_id": pl.Int32,
            "game_resource_id": pl.Utf8,
            "domestic_production": pl.Float64,
        }
        if regions.is_empty() or not {"id"}.issubset(regions.columns):
            return pl.DataFrame(schema=schema)

        region_lookup: dict[str, int | None] = {}
        for region in regions.iter_rows(named=True):
            region_id = int(region["id"])
            aliases = [region_id]
            aliases.extend(region.get(key) for key in ("iso_region", "hex", "postal"))
            for alias in aliases:
                normalized = str(alias or "").strip().upper().lstrip("#")
                if not normalized:
                    continue
                previous = region_lookup.get(normalized, region_id)
                region_lookup[normalized] = region_id if previous == region_id else None

        records_by_id: dict[str, dict[str, Any]] = {}
        for data_dir in self.config.get_data_dirs():
            target_dir = data_dir / "countries" / "countries_res"
            if not target_dir.exists():
                continue

            for file_path in sorted(target_dir.glob("*.toml")):
                country_id = file_path.stem.strip().upper()
                data = self._read_required_toml(file_path, "country resource")
                for region_key, region_data in self._regional_resource_entries(
                    data.get("regional_resources", {})
                ):
                    normalized_region = str(region_key or "").strip().upper().lstrip("#")
                    region_id = region_lookup.get(normalized_region)
                    if region_id is None:
                        raise ValueError(
                            f"{file_path.name} references unknown or ambiguous region '{region_key}'."
                        )
                    for resource_id, resource_data in region_data.items():
                        if not resource_id:
                            raise ValueError(f"{file_path.name} contains an empty regional resource ID.")
                        if isinstance(resource_data, dict):
                            unsupported_fields = set(resource_data) - {
                                "production",
                                "domestic_production",
                            }
                            if unsupported_fields:
                                raise ValueError(
                                    f"{file_path.name} has unsupported regional fields for "
                                    f"'{resource_id}': {sorted(unsupported_fields)}."
                                )
                            raw_amount = resource_data.get(
                                "production",
                                resource_data.get("domestic_production"),
                            )
                        else:
                            raw_amount = resource_data

                        amount = self._validated_nonnegative(
                            raw_amount,
                            f"{file_path.name} has invalid regional production for '{resource_id}'.",
                        )
                        record_id = f"{country_id}:{region_id}:{resource_id}"
                        records_by_id[record_id] = {
                            "id": record_id,
                            "country_id": country_id,
                            "region_id": int(region_id),
                            "game_resource_id": str(resource_id),
                            "domestic_production": amount,
                        }

        rows = [row for row in records_by_id.values() if row["domestic_production"] > 0.0]
        return pl.DataFrame(rows, schema=schema, strict=False) if rows else pl.DataFrame(schema=schema)

    def _regional_resource_entries(self, regional_resources: Any) -> list[tuple[Any, dict[str, Any]]]:
        if isinstance(regional_resources, list):
            entries = []
            for entry in regional_resources:
                if not isinstance(entry, dict):
                    raise ValueError("Each regional_resources list entry must be a mapping.")
                region_key = entry.get("region_id", entry.get("region"))
                resources = entry.get("resources", {})
                if region_key is None or not isinstance(resources, dict):
                    raise ValueError("Regional resources require a region identifier and resource mapping.")
                entries.append((region_key, resources))
            return entries

        if not isinstance(regional_resources, dict):
            raise ValueError("regional_resources must be a mapping or a list of mappings.")

        entries = []
        for region_key, region_data in regional_resources.items():
            if not isinstance(region_data, dict):
                raise ValueError(f"Regional resource entry '{region_key}' must be a mapping.")
            resources = region_data.get("resources")
            if not isinstance(resources, dict):
                resources = {
                    key: value
                    for key, value in region_data.items()
                    if key not in {"region", "region_id", "name"}
                }
            entries.append((region_data.get("region_id", region_data.get("region", region_key)), resources))
        return entries

    def _validated_nonnegative(self, value: Any, message: str) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(message) from error
        if not math.isfinite(number) or number < 0.0:
            raise ValueError(message)
        return number
