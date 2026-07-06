import dataclasses
from pathlib import Path
from typing import Any, Dict, List, Sequence, get_type_hints

import orjson
import polars as pl
import rtoml
from PIL import Image

from src.shared.config import GameConfig
from src.shared.state import GameState


class DataLoader:
    """
    Responsible for loading GameState data from two sources:
    1. Static Assets (TSV/TOML) -> For starting a fresh game (load_initial_state).
    2. User Saves (Parquet/JSON) -> For loading a saved session (load_save).
    """

    def __init__(self, config: GameConfig):
        self.config = config
        self.save_root = config.project_root / "user_data" / "saves"

    # =========================================================================
    #  PART 1: SAVE GAME LOADING (Reflection Based)
    # =========================================================================

    def load_save(self, save_name: str) -> GameState:
        """
        Reconstructs a GameState from a save directory using type-driven reflection.
        """
        save_dir = self.save_root / save_name
        if not save_dir.exists():
            raise FileNotFoundError(f"Save '{save_name}' not found.")

        print(f"[DataLoader] Loading save '{save_name}'...")

        meta_path = save_dir / "meta.json"
        if meta_path.exists():
            with open(meta_path, "rb") as f:
                meta_data = orjson.loads(f.read())
        else:
            print(f"[DataLoader] Warning: meta.json not found for {save_name}. Using defaults.")
            meta_data = {}

        constructor_args = {}
        type_hints = get_type_hints(GameState)

        for field in dataclasses.fields(GameState):
            key = field.name
            target_type = type_hints.get(key)

            if key == "tables":
                tables = {}
                sub_dir = save_dir / key
                if sub_dir.exists():
                    for p_file in sub_dir.glob("*.parquet"):
                        tables[p_file.stem] = pl.read_parquet(p_file)
                constructor_args[key] = tables

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
        print(f"[DataLoader] Save loaded successfully. Tick: {state.globals.get('tick', 0)}")
        return state

    # =========================================================================
    #  PART 2: INITIAL STATE COMPILATION (Static Assets)
    # =========================================================================

    def load_initial_state(self) -> GameState:
        print("[DataLoader] Compiling state (Hex-Key Mode)...")
        state = GameState()

        regions_df = self._load_master_regions()

        if not regions_df.is_empty():
            regions_df = self._generate_int_id(regions_df)
            regions_df = self._enrich_regions_data(regions_df)
            regions_df = self._add_region_geo_columns(regions_df)

            num_cols = [c for c, t in regions_df.schema.items() if t in (pl.Float64, pl.Int64, pl.Int32)]
            if num_cols:
                regions_df = regions_df.with_columns(pl.col(num_cols).fill_null(0))

            state.update_table("regions", regions_df)
            print(f"[DataLoader] Regions loaded: {len(regions_df)}")
        else:
            print("[DataLoader] CRITICAL: No regions found!")
            state.update_table("regions", pl.DataFrame())

        countries_df = self._load_countries(regions_df)
        state.update_table("countries", countries_df if not countries_df.is_empty() else pl.DataFrame())

        for table_name, world_df in self._load_world_tables().items():
            print(f"[DataLoader] Loading world table: {table_name}")
            state.update_table(table_name, world_df)

        prod_df = self._load_domestic_production()
        state.update_table("domestic_production", prod_df)

        return state

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
        except Exception as e:
            print(f"[DataLoader] Error reading {path.name}: {e}")
            return pl.DataFrame()

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
        if len(valid_layers) == 1:
            return valid_layers[0]

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
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = rtoml.load(f)
        except Exception as e:
            print(f"[DataLoader] Failed to parse world TOML {path.name}: {e}")
            return pl.DataFrame()

        if not data:
            return pl.DataFrame()

        if path.stem in data:
            raw = data[path.stem]
        elif len(data) == 1:
            raw = next(iter(data.values()))
        else:
            print(f"[DataLoader] World TOML {path.name} has no '{path.stem}' root table.")
            return pl.DataFrame()

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
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = rtoml.load(f)
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
                except Exception as e:
                    print(f"[DataLoader] Failed to parse TOML {file_path.name}: {e}")

        if records:
            return pl.DataFrame(records)
        return pl.DataFrame(
            {"country_id": [], "game_resource_id": [], "domestic_production": []},
            schema={"country_id": pl.Utf8, "game_resource_id": pl.Utf8, "domestic_production": pl.Float64},
        )
