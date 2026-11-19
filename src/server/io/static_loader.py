import hashlib
import logging
import math
import re
import unicodedata
from pathlib import Path
from typing import Sequence, Any, Dict, List

import polars as pl
import rtoml
from PIL import Image

from src.core.paths import resolve_region_map_path
from src.shared.config import GameConfig
from src.shared.state import GameState

logger = logging.getLogger(__name__)


def warn_unregistered_region_owners(regions: pl.DataFrame, countries: pl.DataFrame) -> None:
    """Identify unresolved owner codes after all startup layers have been applied."""
    if "owner" not in regions.columns:
        return
    country_ids = set(countries["id"].drop_nulls()) if "id" in countries.columns else set()
    owner_counts = (
        regions.filter(pl.col("owner").is_not_null() & (pl.col("owner") != ""))
        .group_by("owner").len().sort("owner")
    )
    unresolved = [f"{owner} ({count})" for owner, count in owner_counts.iter_rows() if owner not in country_ids]
    if unresolved:
        logger.warning("Region owners missing from the country roster: %s", ", ".join(unresolved))


def merge_layered_records(layers: Sequence[pl.DataFrame], keys: Sequence[str]) -> pl.DataFrame:
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

class StaticAssetLoader:
    """
    Responsible for loading immutable game data from static files (TSV/TOML).
    It populates the initial GameState with Definitions, Entities, and World State.

    Architecture:
    1. Definitions (data/definitions/*.toml): Static rules (resources, unit types).
    2. Map & Regions (data/map/*.tsv): Topography and geography.
    3. Countries (data/countries/*.tsv): Entity attributes.
    4. World State (data/world/*.toml): Relational data (wars, diplomacy, environment).

    This separation ensures that rules exist before entities, and entities exist 
    before relationships are established between them.
    """

    def __init__(self, config: GameConfig):
        self.config = config

    def compile_initial_state(self) -> GameState:
        """
        Aggregates data from all active mods to build the starting world state.
        Data loading order is critical for dependency resolution.
        """
        print("[StaticLoader] Compiling immutable game data...")
        state = GameState()
        
        # PHASE 1: Load Definitions
        # These are the "blueprints" of the game (e.g., what is 'Iron'?).
        # Other systems might reference these IDs immediately.
        definitions = self._load_toml_collection("definitions")
        for key, df in definitions.items():
            # We prefix definitions tables to avoid collision (e.g., 'def_resources')
            state.update_table(f"def_{key}", df)

        # PHASE 2: Load Entities (Backbone)
        # These are the physical actors and locations in the game.
        state.update_table("regions", self._load_regions())
        state.update_table("countries", self._load_countries())
        warn_unregistered_region_owners(state.get_table("regions"), state.get_table("countries"))
        state.update_table(
            "country_identity_distribution",
            self.load_country_identity_distribution(state.get_table("countries")),
        )
        
        # PHASE 3: Load World State (Relations)
        # These are interactions or global conditions involving entities.
        # e.g., Wars, Diplomacy, Global Market.
        world_data = self._load_toml_collection("world")
        for key, df in world_data.items():
            state.update_table(key, df)
        
        return state

    def load_definitions(self) -> Dict[str, pl.DataFrame]:
        """Load layered static definitions for consumers that enrich their own state."""
        return self._load_toml_collection("definitions")

    # =========================================================================
    # SECTION: TSV LOADING (Entities & Map)
    # =========================================================================

    def _load_regions(self) -> pl.DataFrame:
        master_df = self.load_master_regions()
        if master_df.is_empty():
            return master_df
        return self._add_region_geo_columns(self._generate_runtime_ids(master_df))

    def load_master_regions(self) -> pl.DataFrame:
        """Merge region layers by normalized map color before deriving runtime IDs."""
        layers = []
        for data_dir in self.config.get_data_dirs():
            # Support both new 'regions' folder and legacy 'map' folder
            p_new = data_dir / "regions" / "regions.tsv"
            p_old = data_dir / "map" / "regions.tsv"
            p = p_new if p_new.exists() else p_old
            
            if p.exists():
                print(f"[StaticLoader] Loading regions from {p}")
                frame = self._read_tsv(p)
                if "hex" not in frame.columns:
                    raise ValueError(f"Region data in '{p}' is missing the 'hex' column.")
                frame = frame.with_columns(pl.col("hex").str.strip_chars().str.strip_prefix("#").str.to_uppercase())
                invalid = frame.filter(~pl.col("hex").str.contains(r"^[0-9A-F]{6}$").fill_null(False))
                if not invalid.is_empty():
                    examples = ", ".join(repr(value) for value in invalid["hex"].head(3))
                    raise ValueError(f"Invalid region colors in '{p}': {examples}. Expected six RGB hex digits.")
                layers.append(frame)
        return merge_layered_records(layers, keys=["hex"])

    def _load_countries(self) -> pl.DataFrame:
        """Load the same layered country roster for world startup and static consumers."""

        master_layers: List[pl.DataFrame] = []
        for data_dir in self.config.get_data_dirs():
            master_path = data_dir / "countries" / "countries.tsv"
            if master_path.exists():
                master_layers.append(self._read_tsv(master_path))

        main_df = merge_layered_records(master_layers, keys=["id"])
        if main_df.is_empty():
            return pl.DataFrame()

        layered_extensions: Dict[str, List[pl.DataFrame]] = {}
        for data_dir in self.config.get_data_dirs():
            target_dir = data_dir / "countries"
            if not target_dir.exists():
                continue

            for file_path in target_dir.glob("countries_*.tsv"):
                aux_df = self._read_tsv(file_path)
                if "id" not in aux_df.columns:
                    continue
                layered_extensions.setdefault(file_path.name, []).append(aux_df)

        for file_name in sorted(layered_extensions):
            merged_extension = merge_layered_records(layered_extensions[file_name], keys=["id"])
            if merged_extension.is_empty() or merged_extension.columns == ["id"]:
                continue

            print(f"[DataLoader] Merging country data: {file_name}")
            main_df = main_df.join(merged_extension, on="id", how="left")

        num_cols = [c for c, t in main_df.schema.items() if t in (pl.Float64, pl.Int64, pl.Int32)]
        if num_cols:
            main_df = main_df.with_columns(pl.col(num_cols).fill_null(0))

        print(f"[DataLoader] Countries loaded: {len(main_df)} rows.")
        return main_df

    def load_country_identity_distribution(self, countries: pl.DataFrame) -> pl.DataFrame:
        """Flattens bundled country identity estimates into a normalized runtime table."""
        schema = {
            "country_id": pl.Utf8,
            "identity_type": pl.Utf8,
            "identity_id": pl.Utf8,
            "display_name": pl.Utf8,
            "population_share": pl.Float64,
            "source_name": pl.Utf8,
            "source_year": pl.Int32,
            "source_reference": pl.Utf8,
            "source_note": pl.Utf8,
            "is_other_bucket": pl.Boolean,
        }
        if countries.is_empty() or "id" not in countries.columns:
            return pl.DataFrame(schema=schema)

        valid_countries = {
            str(country_id or "").strip().upper()
            for country_id in countries.get_column("id").to_list()
        }
        profiles: dict[
            tuple[str, str],
            tuple[dict[str, float], dict[str, str], str, dict[str, str] | None],
        ] = {}
        files = (
            ("language", "country_languages.toml", "country_languages"),
            ("religion", "country_religions.toml", "country_religions"),
        )

        # Later mod layers replace profiles, while absent source notes inherit from base data.
        data_dirs = self.config.get_data_dirs()
        language_sources: dict[str, dict[str, str]] = {}
        for data_dir in data_dirs:
            language_sources.update(self._load_country_language_source_context(data_dir))
        for data_dir in data_dirs:
            for identity_type, filename, section_name in files:
                file_path = data_dir / "countries" / filename
                if not file_path.is_file():
                    continue
                try:
                    with file_path.open("r", encoding="utf-8") as handle:
                        raw_profiles = rtoml.load(handle).get(section_name, {})
                except Exception as error:
                    raise RuntimeError(f"Failed to parse country identity data: {file_path}") from error
                if not isinstance(raw_profiles, dict):
                    continue
                for country_id, values in raw_profiles.items():
                    country = str(country_id or "").strip().upper()
                    if country not in valid_countries or not isinstance(values, dict):
                        continue
                    parsed: dict[str, float] = {}
                    display_names: dict[str, str] = {}
                    for display_name, raw_share in values.items():
                        name = str(display_name or "").strip()
                        identity_id = self._identity_slug(name)
                        try:
                            share = float(raw_share)
                        except (TypeError, ValueError, OverflowError):
                            continue
                        if not name or not identity_id or not math.isfinite(share) or not (share > 0.0):
                            continue
                        parsed[identity_id] = parsed.get(identity_id, 0.0) + share
                        display_names[identity_id] = name
                    if parsed:
                        language_source = (
                            language_sources.get(country)
                            if identity_type == "language"
                            else None
                        )
                        profiles[(identity_type, country)] = (
                            parsed,
                            display_names,
                            filename,
                            language_source,
                        )

        rows: list[dict[str, Any]] = []
        for (identity_type, country_id), (
            values,
            display_names,
            filename,
            language_source,
        ) in sorted(profiles.items()):
            total = sum(values.values())
            if not math.isfinite(total) or total <= 0.0:
                continue
            source_note = "Bundled gameplay estimate; the original census/source year is not recorded."
            source_reference = filename
            if language_source is not None:
                source_country = language_source.get("source_country", "")
                source_status = language_source.get("source_status", "")
                source_field = language_source.get("source_field", "")
                source_url = language_source.get("source_url", "")
                if source_status == "not_separate_in_2001":
                    source_reference = (
                        f"{filename}; no separate 2001 Factbook entry for {country_id} "
                        f"({source_url})"
                    )
                else:
                    source_reference = (
                        f"Population shares: {filename}; contextual language source: "
                        f"CIA World Factbook 2001, {source_country or country_id} "
                        f"({source_url})"
                    )
                source_note = (
                    "The displayed population share remains an OpenPower gameplay "
                    "estimate; this country-level source description does not validate "
                    "the row's numeric share. The 2001 Factbook edition does not give "
                    "a consistent observation year for language descriptions. "
                )
                if source_status == "reported" and source_field:
                    source_note += f"Factbook Languages field: {source_field}"
                else:
                    source_note += language_source.get("source_note", "No language field is recorded.")
                supplemental_context = language_source.get("supplemental_context", "")
                supplemental_reference = language_source.get("supplemental_reference", "")
                if supplemental_context:
                    source_note += f" {supplemental_context}"
                if supplemental_reference:
                    source_reference += f"; {supplemental_reference}"
            for identity_id, value in sorted(values.items()):
                display_name = display_names.get(identity_id, identity_id.replace("_", " ").title())
                rows.append(
                    {
                        "country_id": country_id,
                        "identity_type": identity_type,
                        "identity_id": identity_id,
                        "display_name": display_name,
                        "population_share": (value / total) * 100.0,
                        "source_name": "OpenPower bundled estimate",
                        "source_year": 0,
                        "source_reference": source_reference,
                        "source_note": source_note,
                        "is_other_bucket": self._is_identity_other_bucket(identity_id),
                    }
                )
        return pl.DataFrame(rows, schema=schema, strict=False)

    @staticmethod
    def _load_country_language_source_context(data_dir: Path) -> dict[str, dict[str, str]]:
        """Read optional historical language notes without treating them as shares."""
        source_path = data_dir / "sources" / "2001" / "country_languages_factbook_2001.tsv"
        contexts: dict[str, dict[str, str]] = {}
        if source_path.is_file():
            try:
                source_frame = pl.read_csv(
                    source_path,
                    separator="\t",
                    schema_overrides={
                        "country_id": pl.Utf8,
                        "source_country": pl.Utf8,
                        "source_status": pl.Utf8,
                        "source_field": pl.Utf8,
                        "source_note": pl.Utf8,
                        "source_url": pl.Utf8,
                    },
                )
            except Exception as error:
                raise RuntimeError(
                    f"Failed to read country language source context: {source_path}"
                ) from error

            contexts = {
                str(row.get("country_id") or "").strip().upper(): {
                    key: str(row.get(key) or "").strip()
                    for key in (
                        "source_country",
                        "source_status",
                        "source_field",
                        "source_note",
                        "source_url",
                    )
                }
                for row in source_frame.iter_rows(named=True)
                if str(row.get("country_id") or "").strip()
            }

        supplemental_path = data_dir / "sources" / "2001" / "country_languages_supplemental_context_2001.tsv"
        if not supplemental_path.is_file():
            return contexts

        try:
            supplemental_frame = pl.read_csv(
                supplemental_path,
                separator="\t",
                schema_overrides={
                    "country_id": pl.Utf8,
                    "context_type": pl.Utf8,
                    "source_year": pl.Int32,
                    "source_name": pl.Utf8,
                    "source_text": pl.Utf8,
                    "source_note": pl.Utf8,
                    "source_url": pl.Utf8,
                    "source_reference": pl.Utf8,
                },
            )
        except Exception as error:
            raise RuntimeError(
                f"Failed to read supplemental country language context: {supplemental_path}"
            ) from error

        for row in supplemental_frame.iter_rows(named=True):
            country_id = str(row.get("country_id") or "").strip().upper()
            if not country_id:
                continue
            source_year = row.get("source_year")
            context = (
                f"Supplementary {str(row.get('context_type') or 'historical').strip()} context "
                f"({str(row.get('source_name') or '').strip()}, source year {source_year}): "
                f"{str(row.get('source_text') or '').strip()} "
                f"{str(row.get('source_note') or '').strip()}"
            ).strip()
            reference = (
                f"{str(row.get('source_reference') or row.get('source_name') or '').strip()} "
                f"({str(row.get('source_url') or '').strip()})"
            ).strip()
            source = contexts.setdefault(
                country_id,
                {
                    key: ""
                    for key in (
                        "source_country",
                        "source_status",
                        "source_field",
                        "source_note",
                        "source_url",
                    )
                },
            )
            if context:
                source["supplemental_context"] = " ".join(
                    value for value in (source.get("supplemental_context", ""), context) if value
                )
            if reference:
                source["supplemental_reference"] = "; ".join(
                    value for value in (source.get("supplemental_reference", ""), reference) if value
                )

        return contexts

    @staticmethod
    def _identity_slug(display_name: str) -> str:
        normalized = unicodedata.normalize("NFKD", str(display_name or ""))
        ascii_name = normalized.encode("ascii", "ignore").decode("ascii").lower()
        slug = re.sub(r"[^a-z0-9]+", "_", ascii_name).strip("_")
        if slug:
            return slug
        # Keep non-Latin labels addressable without losing their display text.
        return f"group_{hashlib.sha1(str(display_name).encode('utf-8')).hexdigest()[:12]}"

    @staticmethod
    def _is_identity_other_bucket(identity_id: str) -> bool:
        return identity_id in {"other", "others", "unspecified", "unclassified"}

    def _read_tsv(self, path: Path) -> pl.DataFrame:
        """
        Robust TSV reader using Polars.
        Forces 'hex' column to String to prevent data corruption (00FF00 -> 255).
        """
        try:
            df = pl.read_csv(
                path, 
                separator="\t", 
                ignore_errors=True, 
                infer_schema_length=1000, 
                schema_overrides={"hex": pl.String} 
            )
            # Filter out internal columns (starting with underscore)
            valid_cols = [c for c in df.columns if not c.startswith("_")]
            return df.select(valid_cols)
        except Exception as error:
            raise RuntimeError(f"Failed to read required static TSV: {path}") from error

    def _generate_runtime_ids(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Converts Hex Strings (e.g. '#FF0000') to Int32 IDs.
        Formula: B + (G * 256) + (R * 65536). 
        Used for O(1) lookups in the rendering pipeline.
        """
        # Ensure format is uppercase #RRGGBB
        df = df.with_columns(
            pl.when(pl.col("hex").str.starts_with("#"))
            .then(pl.col("hex"))
            .otherwise(pl.lit("#") + pl.col("hex"))
            .str.to_uppercase()
            .alias("hex")
        )

        # Slice hex string into components and compute integer ID
        df = df.with_columns([
            pl.col("hex").str.slice(1, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_r"),
            pl.col("hex").str.slice(3, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_g"),
            pl.col("hex").str.slice(5, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_b"),
        ])
        
        df = df.with_columns(
            (pl.col("_b") + (pl.col("_g") * 256) + (pl.col("_r") * 65536)).cast(pl.Int32).alias("id")
        )
        
        return df.drop(["_r", "_g", "_b"])

    def _add_region_geo_columns(self, regions_df: pl.DataFrame) -> pl.DataFrame:
        if regions_df.is_empty() or not {"center_x", "center_y"}.issubset(set(regions_df.columns)):
            return regions_df

        map_width, map_height = self._get_region_map_dimensions(regions_df)
        return regions_df.with_columns(
            (90.0 - (pl.col("center_y").cast(pl.Float64) / float(map_height)) * 180.0).alias("latitude"),
            ((pl.col("center_x").cast(pl.Float64) / float(map_width)) * 360.0 - 180.0).alias("longitude"),
        )

    def _get_region_map_dimensions(self, regions_df: pl.DataFrame) -> tuple[int, int]:
        fallback = resolve_region_map_path(self.config)
        if fallback.exists():
            return self._read_image_size(fallback)

        max_x = int(regions_df["center_x"].max() or 1) + 1
        max_y = int(regions_df["center_y"].max() or 1) + 1
        return max_x, max_y

    def _read_image_size(self, path: Path) -> tuple[int, int]:
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(path) as image:
            return image.size

    # =========================================================================
    # SECTION: TOML LOADING (Definitions & World)
    # =========================================================================

    def _load_toml_collection(self, folder_name: str) -> Dict[str, pl.DataFrame]:
        """
        Scans a specific folder (e.g., 'world' or 'definitions') in all mods.
        Merges TOML files with the same name across mods into single DataFrames.
        
        This generic approach allows us to add new data categories (like 'technology')
        without changing the loader code.
        """
        collected_data: Dict[str, List[pl.DataFrame]] = {}

        for data_dir in self.config.get_data_dirs():
            target_dir = data_dir / folder_name
            if not target_dir.exists():
                continue

            for file_path in target_dir.glob("*.toml"):
                key_name = file_path.stem  # e.g., 'wars' from 'wars.toml'
                
                df = self._parse_toml_file(file_path, key_name)
                if not df.is_empty():
                    if key_name not in collected_data:
                        collected_data[key_name] = []
                    collected_data[key_name].append(df)
                    print(f"[StaticLoader] Loaded '{folder_name}/{key_name}' from {file_path.name}")

        # Concatenate collected DataFrames
        # 'diagonal_relaxed' handles cases where mods might add extra properties/columns
        final_tables = {}
        for key, dfs in collected_data.items():
            if dfs:
                final_tables[key] = pl.concat(dfs, how="diagonal_relaxed")
        
        return final_tables

    def _parse_toml_file(self, file_path: Path, key: str) -> pl.DataFrame:
        """
        Parses a single TOML file and detects its structure strategy.
        Uses 'rtoml' for high-performance parsing.

        Supported Strategies:
        
        1. LIST STRATEGY (Entity Component System style)
           Used for lists of definitions or events.
           Key matches filename: [[units]] inside units.toml
           
           Example 'units.toml':
               [[units]]
               id = "tank_t1"
               attack = 10
               
           Result: | id | attack |

        2. MATRIX STRATEGY (Adjacency Matrix / Dictionary style)
           Used for defining relationships between entities.
           Nested dictionaries: [diplomacy.USA] GBR = 100
           
           Result: | source | target | value |
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = rtoml.load(f)
        except Exception as error:
            raise RuntimeError(f"Failed to parse required static TOML: {file_path}") from error

        raw_content = data.get(key)

        if raw_content is None:
            # Graceful failure: return empty if key is missing (e.g. empty file)
            return pl.DataFrame()

        # Strategy 1: Normalized List
        if isinstance(raw_content, list):
            return pl.from_dicts(raw_content)

        # Strategy 2: Adjacency Matrix / Nested Dictionary
        elif isinstance(raw_content, dict):
            # We need to distinguish between a Matrix (Source -> Target -> Value)
            # and an Entity Dictionary (Entity_ID -> {Properties})
            # If the first value is a dict, and it contains 'production' or other properties, 
            # it's likely an Entity Dictionary.
            first_val = next(iter(raw_content.values())) if raw_content else None
            if isinstance(first_val, dict) and any(k in first_val for k in ['production', 'legal', 'id', 'name']):
                return self._flatten_entity_dict(raw_content)
            return self._flatten_matrix(raw_content)

        else:
            print(f"[StaticLoader] Unknown data structure in {file_path.name} under key '{key}'")
            return pl.DataFrame()

    def _flatten_entity_dict(self, entity_data: Dict[str, Dict[str, Any]]) -> pl.DataFrame:
        """
        Converts a dictionary of entities into a normalized table.
        [section.entity_id] prop = value
        
        Result: | id | prop1 | prop2 |
        """
        rows = []
        for entity_id, properties in entity_data.items():
            if not isinstance(properties, dict):
                continue
            row = {"id": entity_id}
            row.update(properties)
            rows.append(row)
        
        return pl.from_dicts(rows)

    def _flatten_matrix(self, matrix_data: Dict[str, Any]) -> pl.DataFrame:
        """
        Flattens a nested dictionary structure into a normalized table.
        
        Handles two types of values:
        1. Scalar: USA -> GBR = 100 (becomes 'value' column)
        2. Complex: USA -> GBR = { trust=100, pact=true } (columns unrolled)
        """
        rows = []
        
        # Iterate through Source entities
        for source_tag, targets in matrix_data.items():
            if not isinstance(targets, dict):
                continue

            # Iterate through Target entities
            for target_tag, value in targets.items():
                row = {
                    "source": source_tag,
                    "target": target_tag
                }

                if isinstance(value, dict):
                    # Complex value: merge dict into row
                    row.update(value)
                else:
                    # Simple value: assign to generic 'value' column
                    row["value"] = value
                
                rows.append(row)

        if not rows:
            return pl.DataFrame()

        return pl.from_dicts(rows)
