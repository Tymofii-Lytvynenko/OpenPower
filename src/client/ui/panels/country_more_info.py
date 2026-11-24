from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from math import isfinite

import polars as pl

from src.client.renderers.country_region_map import (
    CountryMapTexture,
    CountryRegionMapTextureCache,
)
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.gml_layout import (
    active_gml_layout,
    draw_gml_separator,
    get_gml_layout,
    resume_gml_layout,
    suspend_gml_layout,
)
from src.client.ui.panels.shared.panel_data import (
    as_percent,
    get_country_row,
    resolve_country_name,
    safe_float,
    safe_int,
    safe_text,
)
from src.core.map_data import RegionMapData


@dataclass(frozen=True, slots=True)
class ShareRow:
    label: str
    percent: float
    value: str
    color: tuple


@dataclass(frozen=True, slots=True)
class PopulationBand:
    label: str
    value: int
    percent: float


@dataclass(frozen=True, slots=True)
class PartyRosterEntry2001:
    display_name: str
    leaders_text: str
    leader_status: str
    source_entry: str
    source_name: str = ""
    source_reference: str = ""
    source_url: str = ""
    source_note: str = ""


@dataclass(frozen=True, slots=True)
class PartyRosterContext2001:
    status: str = "source_coverage_unavailable"
    source_country: str = ""
    source_reference: str = ""
    source_url: str = ""
    source_note: str = ""
    entries: tuple[PartyRosterEntry2001, ...] = ()
    supplemental_entries: tuple[PartyRosterEntry2001, ...] = ()
    source_notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ElectionResultEntry2001:
    result_label: str
    votes: int | None
    vote_share_pct: float | None
    seats: int | None
    general_seats: int | None
    special_seats: int | None


@dataclass(frozen=True, slots=True)
class ElectionResultEvent2001:
    event_id: str
    election_date: str
    additional_election_date: str
    result_date: str
    geography: str
    result_scope: str
    source_name: str
    source_reference: str
    source_url: str
    source_note: str
    results: tuple[ElectionResultEntry2001, ...] = ()


SOURCE_PARTY_FIELD_2001 = "Political parties and leaders"


POPULATION_SOURCE_TOOLTIP = (
    "Age cohorts use retrospective WorldPop 2001 1 km estimates where a source cell maps to the region. "
    "Published territory counts are used when available; if their age breakdown is unavailable, cohorts are "
    "estimated from available country-level age shares. All 4,559 regions now have a sourced observation, "
    "documented estimate, staffing model, or explicit uninhabited-zero assumption; none silently retain an "
    "unverified prior baseline. Per-region sources and methods are recorded in "
    "modules/base/data/sources/2001/regional_population_provenance.tsv."
)
PROTECTED_AREA_SOURCE_TOOLTIP = (
    "UN Statistics Division table, observation year 2000, published in a table last updated in 2010. "
    "Nationally designated terrestrial protected-area extent is reported as a share of total country surface, "
    "including inland waters. The measure includes protection categories beyond national parks and can include "
    "sites whose designation year is unknown. Values are rounded to 0.1 percentage point. "
    "Source: https://unstats.un.org/unsd/environment/TerrestrialProtectedAreas.htm"
)
OTHER_LAND_SOURCE_TOOLTIP = (
    "FAOSTAT Land Use, observation year 2001. Other land is the source's residual land-use category; it is not "
    "a measure of land that cannot be used. The percentage is Other land area divided by FAOSTAT Land area."
)
HISTORICAL_REFERENCE_YEAR = 2001


@dataclass(frozen=True, slots=True)
class CountryMoreInfoModel:
    tag: str
    name: str
    region_ids: tuple[int, ...]
    region_count: int
    land_area_km2: float
    world_area_share_pct: float
    population_total: int
    population_bands: tuple[PopulationBand, ...]
    population_available: bool
    density_per_km2: float
    human_dev_pct: float | None
    world_human_dev_pct: float | None
    infrastructure_pct: float
    telecom_pct: float
    land_area_available: bool
    poverty_pct: float
    fertility_rate: float
    life_expectancy: float
    composition_rows: tuple[ShareRow, ...]
    production_rows: tuple[ShareRow, ...]
    region_summary: str
    land_use_areas_km2: dict[str, float] = field(default_factory=dict)
    inland_water_area_km2: float | None = None
    birth_rate_per_1000: float | None = None
    death_rate_per_1000: float | None = None
    historical_metrics: dict = field(default_factory=dict)
    world_human_dev_year: int | None = None
    party_roster_2001: PartyRosterContext2001 = field(
        default_factory=PartyRosterContext2001
    )
    election_results_2001: tuple[ElectionResultEvent2001, ...] = ()


class CountryMoreInfoPresenter:
    """Builds a country info view model from data-oriented game tables."""

    def build(self, state, country_tag: str) -> CountryMoreInfoModel:
        tag = safe_text(country_tag, "Unknown")
        country_row = get_country_row(state, tag)
        country_regions = self._country_regions(state, tag)

        region_ids = self._region_ids(country_regions)
        population_bands = self._population_bands(country_regions)
        population_total = sum(band.value for band in population_bands)
        land_column = "land_area_km2" if "land_area_km2" in country_regions.columns else "area_km2"
        land_area = self._sum_column(country_regions, land_column)
        world_area = self._sum_column(getattr(state, "tables", {}).get("regions"), land_column)
        regional_areas = {}
        for column in (
            "arable_area_km2", "forest_area_km2", "protected_area_km2",
            "other_land_area_km2", "inland_water_area_km2",
        ):
            available = f"{column}_available"
            if (
                not country_regions.is_empty()
                and {column, available}.issubset(country_regions.columns)
                and country_regions.get_column(available).fill_null(False).all()
            ):
                regional_areas[column] = self._sum_column(country_regions, column)
        population_available = not country_regions.is_empty() and {
            "pop_14",
            "pop_15_64",
            "pop_65",
        }.issubset(country_regions.columns)
        land_area_available = (
            not country_regions.is_empty() and land_column in country_regions.columns
        )
        countries = getattr(state, "tables", {}).get("countries")
        world_hdi = None
        if countries is not None and "human_dev" in countries.columns:
            values = countries.get_column("human_dev").cast(pl.Float64, strict=False).drop_nulls()
            valid = [value for value in values if isfinite(value) and 0 <= value <= 1]
            if valid:
                world_hdi = sum(valid) / len(valid) * 100.0

        return CountryMoreInfoModel(
            tag=tag,
            name=resolve_country_name(state, tag),
            region_ids=region_ids,
            region_count=len(region_ids),
            land_area_km2=land_area,
            world_area_share_pct=(land_area / world_area * 100.0)
            if world_area > 0
            else 0.0,
            population_total=population_total,
            population_bands=population_bands,
            population_available=population_available,
            birth_rate_per_1000=self._population_weighted_rate(country_regions, "birth_rate_per_1000")
            if population_available else None,
            death_rate_per_1000=country_row.get("death_rate_per_1000"),
            density_per_km2=(population_total / land_area) if land_area > 0 else 0.0,
            human_dev_pct=as_percent(country_row["human_dev"])
            if country_row.get("human_dev") is not None
            else None,
            world_human_dev_pct=world_hdi,
            # These are national service indices; budget ratios describe spending allocation.
            infrastructure_pct=as_percent(country_row.get("infrastructure_index")),
            telecom_pct=as_percent(country_row.get("telecom_index")),
            land_area_available=land_area_available,
            poverty_pct=as_percent(country_row.get("poverty_rate")),
            fertility_rate=safe_float(country_row.get("fertility_rate")),
            life_expectancy=safe_float(country_row.get("life_expectancy")),
            composition_rows=self._composition_rows(country_regions),
            production_rows=self._production_rows(state, tag),
            region_summary=self._region_summary(country_regions),
            land_use_areas_km2=regional_areas,
            inland_water_area_km2=regional_areas.get("inland_water_area_km2"),
            historical_metrics=dict(country_row),
            world_human_dev_year=None,
            party_roster_2001=self._party_roster_2001(state, tag),
            election_results_2001=self._election_results_2001(state, tag),
        )

    @staticmethod
    def _historical_world_hdi(state) -> tuple[float | None, int | None]:
        table = getattr(state, "tables", {}).get("historical_world_indicators")
        if (
            table is None
            or table.is_empty()
            or not {"id", "year", "reference_human_dev"}.issubset(table.columns)
        ):
            return None, None
        rows = table.filter((pl.col("id") == "WLD") & (pl.col("year") == 2001))
        if rows.height != 1:
            return None, None
        try:
            value = float(rows["reference_human_dev"][0])
        except (TypeError, ValueError):
            return None, None
        if not isfinite(value) or not 0 <= value <= 1:
            return None, None
        # Use UNDP's aggregate, whose component weights differ from a mean of country HDIs.
        return value * 100, 2001

    @staticmethod
    def _party_roster_2001(state, country_tag: str) -> PartyRosterContext2001:
        tables = getattr(state, "tables", {})
        party_table = tables.get("country_party_roster_2001")
        coverage_table = tables.get("country_party_roster_coverage_2001")
        supplemental_table = tables.get("country_party_roster_supplemental_2001")
        tag = str(country_tag or "").strip().upper()

        def rows_for_country(table) -> list[dict]:
            if table is None or table.is_empty() or "country_id" not in table.columns:
                return []
            try:
                return [
                    row
                    for row in table.to_dicts()
                    if str(row.get("country_id") or "").strip().upper() == tag
                ]
            except Exception:
                return []

        raw_entries = rows_for_country(party_table)
        raw_supplemental_entries = rows_for_country(supplemental_table)
        coverage_rows = rows_for_country(coverage_table)
        coverage = coverage_rows[0] if coverage_rows else {}
        entries = tuple(
            PartyRosterEntry2001(
                display_name=safe_text(row.get("display_name")),
                leaders_text=safe_text(row.get("leaders_text")),
                leader_status=safe_text(row.get("leader_status"), "not_listed"),
                source_entry=safe_text(row.get("source_entry")),
                source_name=safe_text(row.get("source_name")),
                source_reference=safe_text(row.get("source_reference")),
                source_url=safe_text(row.get("source_url")),
                source_note=safe_text(row.get("source_note")),
            )
            for row in raw_entries
            if safe_text(row.get("display_name"))
        )
        supplemental_entries = tuple(
            PartyRosterEntry2001(
                display_name=safe_text(row.get("display_name")),
                leaders_text=safe_text(row.get("leaders_text")),
                leader_status=safe_text(row.get("leader_status"), "not_reported"),
                source_entry=safe_text(row.get("source_entry")),
                source_name=safe_text(row.get("source_name")),
                source_reference=safe_text(row.get("source_reference")),
                source_url=safe_text(row.get("source_url")),
                source_note=safe_text(row.get("source_note")),
            )
            for row in raw_supplemental_entries
            if safe_text(row.get("display_name"))
        )
        source_notes = tuple(
            dict.fromkeys(
                note
                for note in (safe_text(row.get("source_notes")) for row in raw_entries)
                if note
            )
        )
        status = safe_text(
            coverage.get("status"),
            "reported" if entries else "source_coverage_unavailable",
        )
        first_entry = raw_entries[0] if raw_entries else {}
        return PartyRosterContext2001(
            status=status,
            source_country=safe_text(
                coverage.get("source_country") or first_entry.get("source_country")
            ),
            source_reference=safe_text(
                coverage.get("source_reference") or first_entry.get("source_reference")
            ),
            source_url=safe_text(
                coverage.get("source_url") or first_entry.get("source_url")
            ),
            source_note=safe_text(
                coverage.get("source_note") or first_entry.get("source_note")
            ),
            entries=entries,
            supplemental_entries=supplemental_entries,
            source_notes=source_notes,
        )

    @staticmethod
    def _election_results_2001(
        state, country_tag: str
    ) -> tuple[ElectionResultEvent2001, ...]:
        table = getattr(state, "tables", {}).get("country_election_results")
        if (
            table is None
            or table.is_empty()
            or not {"country_id", "event_id", "result_label"}.issubset(table.columns)
        ):
            return ()

        tag = str(country_tag or "").strip().upper()
        try:
            rows = [
                row
                for row in table.to_dicts()
                if str(row.get("country_id") or "").strip().upper() == tag
            ]
        except Exception:
            return ()

        grouped: dict[str, dict] = {}

        def optional_int(value) -> int | None:
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError, OverflowError):
                return None

        def optional_float(value) -> float | None:
            try:
                result = float(value) if value is not None else None
            except (TypeError, ValueError, OverflowError):
                return None
            return result if result is not None and isfinite(result) else None

        for row in rows:
            event_id = safe_text(row.get("event_id"))
            label = safe_text(row.get("result_label"))
            if not event_id or not label:
                continue
            event = grouped.setdefault(
                event_id,
                {
                    "election_date": safe_text(row.get("election_date")),
                    "additional_election_date": safe_text(
                        row.get("additional_election_date")
                    ),
                    "result_date": safe_text(row.get("result_date")),
                    "geography": safe_text(row.get("geography")),
                    "result_scope": safe_text(row.get("result_scope")),
                    "source_name": safe_text(row.get("source_name")),
                    "source_reference": safe_text(row.get("source_reference")),
                    "source_url": safe_text(row.get("source_url")),
                    "source_note": safe_text(row.get("source_note")),
                    "results": [],
                },
            )
            event["results"].append(
                ElectionResultEntry2001(
                    result_label=label,
                    votes=optional_int(row.get("votes")),
                    vote_share_pct=optional_float(row.get("vote_share_pct")),
                    seats=optional_int(row.get("seats")),
                    general_seats=optional_int(row.get("general_seats")),
                    special_seats=optional_int(row.get("special_seats")),
                )
            )

        return tuple(
            ElectionResultEvent2001(
                event_id=event_id,
                election_date=event["election_date"],
                additional_election_date=event["additional_election_date"],
                result_date=event["result_date"],
                geography=event["geography"],
                result_scope=event["result_scope"],
                source_name=event["source_name"],
                source_reference=event["source_reference"],
                source_url=event["source_url"],
                source_note=event["source_note"],
                results=tuple(event["results"]),
            )
            for event_id, event in grouped.items()
        )

    def _country_regions(self, state, tag: str) -> pl.DataFrame:
        regions = getattr(state, "tables", {}).get("regions")
        if regions is None or regions.is_empty():
            return pl.DataFrame()

        authority_col = "controller" if "controller" in regions.columns else "owner"
        if authority_col not in regions.columns:
            return pl.DataFrame()

        try:
            return regions.filter(pl.col(authority_col) == tag)
        except Exception:
            return pl.DataFrame()

    def _region_ids(self, regions: pl.DataFrame) -> tuple[int, ...]:
        if regions.is_empty() or "id" not in regions.columns:
            return ()
        return tuple(
            int(value)
            for value in regions["id"].drop_nulls().to_list()
            if int(value) > 0
        )

    def _population_weighted_rate(self, regions: pl.DataFrame, column: str) -> float | None:
        if column not in regions.columns:
            return None
        population = pl.sum_horizontal("pop_14", "pop_15_64", "pop_65")
        populated = regions.filter(population > 0)
        rate = pl.col(column)
        if populated.is_empty() or not populated.select(
            rate.is_finite().fill_null(False).all()
        ).item():
            return None
        return populated.select((rate * population).sum() / population.sum()).item()

    def _population_bands(self, regions: pl.DataFrame) -> tuple[PopulationBand, ...]:
        values = (
            ("0-14 years", safe_int(self._sum_column(regions, "pop_14"))),
            ("15-64 years", safe_int(self._sum_column(regions, "pop_15_64"))),
            ("65 years +", safe_int(self._sum_column(regions, "pop_65"))),
        )
        total = sum(value for _, value in values)
        return tuple(
            PopulationBand(label, value, (value / total * 100.0) if total > 0 else 0.0)
            for label, value in values
        )

    def _composition_rows(self, regions: pl.DataFrame) -> tuple[ShareRow, ...]:
        if regions.is_empty():
            return ()

        group_col = (
            "type"
            if "type" in regions.columns
            else "macro_region"
            if "macro_region" in regions.columns
            else ""
        )
        if not group_col:
            return ()

        weight_col = "area_km2" if "area_km2" in regions.columns else ""
        try:
            if weight_col:
                grouped = (
                    regions.group_by(group_col)
                    .agg(
                        pl.col(weight_col).sum().alias("weight"),
                        pl.len().alias("count"),
                    )
                    .sort("weight", descending=True)
                )
                total = float(grouped["weight"].sum() or 0.0)
            else:
                grouped = (
                    regions.group_by(group_col)
                    .agg(pl.len().alias("count"))
                    .sort("count", descending=True)
                )
                total = float(grouped["count"].sum() or 0.0)
        except Exception:
            return ()

        colors = (
            GAMETHEME.colors.info,
            GAMETHEME.colors.positive,
            GAMETHEME.colors.warning,
            GAMETHEME.colors.demographics,
        )
        rows = []
        for index, row in enumerate(grouped.head(4).iter_rows(named=True)):
            weight = safe_float(row.get("weight", row.get("count", 0.0)))
            percent = (weight / total * 100.0) if total > 0 else 0.0
            rows.append(
                ShareRow(
                    label=safe_text(row.get(group_col), "Unknown").title(),
                    percent=percent,
                    value=f"{safe_int(row.get('count'))} regions",
                    color=colors[index % len(colors)],
                )
            )
        return tuple(rows)

    def _production_rows(self, state, tag: str) -> tuple[ShareRow, ...]:
        production = getattr(state, "tables", {}).get("domestic_production")
        if production is None or production.is_empty():
            return ()
        required = {"country_id", "game_resource_id", "domestic_production"}
        if not required.issubset(set(production.columns)):
            return ()

        try:
            grouped = (
                production.filter(pl.col("country_id") == tag)
                .group_by("game_resource_id")
                .agg(pl.col("domestic_production").sum().alias("value"))
                .sort("value", descending=True)
            )
        except Exception:
            return ()

        total = float(grouped["value"].sum() or 0.0) if not grouped.is_empty() else 0.0
        colors = (
            GAMETHEME.colors.economy,
            GAMETHEME.colors.info,
            GAMETHEME.colors.politics,
            GAMETHEME.colors.demographics,
        )
        rows = []
        for index, row in enumerate(grouped.head(4).iter_rows(named=True)):
            value = safe_float(row.get("value"))
            rows.append(
                ShareRow(
                    label=safe_text(row.get("game_resource_id"), "Unknown")
                    .replace("_", " ")
                    .title(),
                    percent=(value / total * 100.0) if total > 0 else 0.0,
                    value=self._format_money(value),
                    color=colors[index % len(colors)],
                )
            )
        return tuple(rows)

    def _region_summary(self, regions: pl.DataFrame) -> str:
        if regions.is_empty():
            return "No regional data loaded for this country."

        for column in ("biome", "macro_region", "type"):
            if column not in regions.columns:
                continue
            values = [
                safe_text(value)
                for value in regions[column].drop_nulls().unique().to_list()
                if safe_text(value)
            ]
            if values:
                return ", ".join(sorted(values)[:6])

        return "Regional metadata is not available."

    def _sum_column(self, df: pl.DataFrame | None, column: str) -> float:
        if df is None or df.is_empty() or column not in df.columns:
            return 0.0
        try:
            return safe_float(df.select(pl.col(column).sum()).item())
        except Exception:
            return 0.0

    def _format_money(self, value: float) -> str:
        if abs(value) >= 1_000_000_000_000:
            return f"$ {value / 1_000_000_000_000:.1f}T"
        if abs(value) >= 1_000_000_000:
            return f"$ {value / 1_000_000_000:.1f}B"
        if abs(value) >= 1_000_000:
            return f"$ {value / 1_000_000:.1f}M"
        return f"$ {value:,.0f}".replace(",", " ")


class CountryMoreInfoPanel:
    def __init__(
        self, map_data_provider: Callable[[], RegionMapData | None] | None = None
    ):
        self._presenter = CountryMoreInfoPresenter()
        self._map_textures = CountryRegionMapTextureCache()
        self._map_data_provider = map_data_provider or (lambda: None)
        self._party_roster_open = False

    def render(self, state, context: PanelRenderContext) -> bool:
        model = self._presenter.build(state, context.target_tag)
        title = f"{model.name.upper()}##COUNTRY_MORE_INFO"
        layout = get_gml_layout("Country_Information_Window")
        viewport = imgui.get_io().display_size
        window_x = (float(viewport.x) - layout.width) / 2.0
        window_y = min(60.0, max(0.0, float(viewport.y) - layout.height))
        with WindowManager.window(
            title,
            x=window_x,
            y=window_y,
            w=layout.width,
            h=layout.height,
            test_id="country_more_info.panel",
        ) as is_open:
            if not is_open:
                self._party_roster_open = False
                return False

            self._render_content(model)
            self._render_party_roster_button(layout)
        if self._party_roster_open:
            self._render_party_roster_dialog(model)
        return True

    def _render_party_roster_button(self, layout) -> None:
        # Keep the source layout fixed; place this informational launcher in the unused title-bar space.
        token = suspend_gml_layout()
        try:
            window_position = imgui.get_window_pos()
            imgui.set_cursor_screen_pos(
                (window_position.x + layout.width - 176.0, window_position.y + 4.0)
            )
            if imgui.button(
                "2001 PARTY ROSTER",
                size=(146.0, 21.0),
                test_id="country.info.party_roster.open",
            ):
                self._party_roster_open = True
        finally:
            resume_gml_layout(token)

    def _render_party_roster_dialog(self, model: CountryMoreInfoModel) -> None:
        viewport = imgui.get_io().display_size
        width = max(320.0, min(760.0, float(viewport.x) - 32.0))
        height = max(280.0, min(640.0, float(viewport.y) - 48.0))
        x = max(0.0, (float(viewport.x) - width) / 2.0)
        y = max(0.0, (float(viewport.y) - height) / 2.0)
        with WindowManager.window(
            "2001 PARTY ROSTER###CountryPartyRoster2001",
            x=x,
            y=y,
            w=width,
            h=height,
            closable=True,
            test_id="country.info.party_roster.dialog",
        ) as dialog_open:
            if dialog_open:
                self._render_party_roster_content(model)
        if not dialog_open:
            self._party_roster_open = False

    def _render_party_roster_content(self, model: CountryMoreInfoModel) -> None:
        roster = model.party_roster_2001
        imgui.text_wrapped(
            f"{model.name} ({model.tag}) — read-only historical party and election records. "
            "Supplemental election sources are separated from the CIA Factbook. No gameplay "
            "support, eligibility, or ruling-party status is added.",
            test_id="country.info.party_roster.intro",
        )
        if roster.status == "reported":
            imgui.text_wrapped(
                f"{len(roster.entries)} named party, bloc, or coalition entries reported for "
                f"{roster.source_country or model.name}.",
                test_id="country.info.party_roster.count",
            )
        else:
            imgui.text_disabled(
                f"Source status: {roster.status}",
                test_id="country.info.party_roster.status",
            )
            imgui.text_wrapped(
                self._party_roster_status_message(model, roster),
                test_id="country.info.party_roster.unavailable_reason",
            )

        imgui.text_wrapped(
            f"Source: {roster.source_reference or 'CIA World Factbook 2001 country coverage ledger'}",
            test_id="country.info.party_roster.reference",
        )
        if roster.source_url:
            imgui.text_wrapped(
                roster.source_url,
                test_id="country.info.party_roster.source_url",
            )
        if roster.source_note:
            imgui.text_wrapped(
                roster.source_note,
                test_id="country.info.party_roster.source_note",
            )

        viewport = imgui.get_io().display_size
        dialog_height = max(280.0, min(640.0, float(viewport.y) - 48.0))
        child_height = max(100.0, dialog_height - 170.0)
        list_open = imgui.begin_child(
            "CountryPartyRosterRows",
            (0.0, child_height),
            True,
            test_id="country.info.party_roster.list",
        )
        try:
            if list_open:
                if roster.entries:
                    for index, entry in enumerate(roster.entries):
                        imgui.text_wrapped(
                            entry.source_entry or entry.display_name,
                            test_id=f"country.info.party_roster.entry.{index}",
                        )
                        if entry.leader_status == "reported":
                            imgui.text_wrapped(
                                f"Leaders: {entry.leaders_text}",
                                test_id=f"country.info.party_roster.leaders.{index}",
                            )
                        elif entry.leader_status == "not_reported":
                            imgui.text_disabled(
                                "Leader not reported in the source entry.",
                                test_id=f"country.info.party_roster.leaders.{index}",
                            )
                        else:
                            imgui.text_disabled(
                                "No leader was listed in the source entry.",
                                test_id=f"country.info.party_roster.leaders.{index}",
                            )
                    if roster.source_notes:
                        imgui.separator_text("Additional Factbook notes")
                        for index, note in enumerate(roster.source_notes):
                            imgui.text_wrapped(
                                note,
                                test_id=f"country.info.party_roster.note.{index}",
                            )
                if roster.supplemental_entries:
                    self._render_supplemental_party_entries(roster.supplemental_entries)
                else:
                    if not roster.entries:
                        imgui.text_disabled(
                            "No source-backed party records are available for this country.",
                            test_id="country.info.party_roster.empty",
                        )
                if model.election_results_2001:
                    self._render_election_results(model.election_results_2001)
        finally:
            imgui.end_child()

        if imgui.button(
            "CLOSE",
            test_id="country.info.party_roster.close",
        ):
            self._party_roster_open = False

    @staticmethod
    def _render_supplemental_party_entries(
        entries: tuple[PartyRosterEntry2001, ...],
    ) -> None:
        imgui.separator_text(
            "Supplemental election and historical political records — not CIA Factbook"
        )
        imgui.text_wrapped(
            f"{len(entries)} supplemental records from separately cited historical context sources.",
            test_id="country.info.party_roster.supplemental_count",
        )
        last_source: tuple[str, str, str, str] | None = None
        for index, entry in enumerate(entries):
            source = (
                entry.source_name,
                entry.source_reference,
                entry.source_url,
                entry.source_note,
            )
            if source != last_source:
                imgui.separator_text(entry.source_name or "Supplemental source")
                if entry.source_reference:
                    imgui.text_wrapped(
                        entry.source_reference,
                        test_id=f"country.info.party_roster.supplemental.reference.{index}",
                    )
                if entry.source_url:
                    imgui.text_wrapped(
                        entry.source_url,
                        test_id=f"country.info.party_roster.supplemental.url.{index}",
                    )
                if entry.source_note:
                    imgui.text_wrapped(
                        entry.source_note,
                        test_id=f"country.info.party_roster.supplemental.note.{index}",
                    )
                last_source = source
            imgui.text_wrapped(
                entry.source_entry or entry.display_name,
                test_id=f"country.info.party_roster.supplemental.entry.{index}",
            )
            if entry.leader_status == "reported":
                imgui.text_wrapped(
                    f"Leaders: {entry.leaders_text}",
                    test_id=f"country.info.party_roster.supplemental.leaders.{index}",
                )
            else:
                imgui.text_disabled(
                    "Leader information was not listed in this result source.",
                    test_id=f"country.info.party_roster.supplemental.leaders.{index}",
                )

    @staticmethod
    def _render_election_results(events: tuple[ElectionResultEvent2001, ...]) -> None:
        imgui.separator_text("Historical election results — read-only")
        for event_index, event in enumerate(events):
            date_text = event.election_date or "date unavailable"
            if event.additional_election_date:
                date_text += f" (additional polling: {event.additional_election_date})"
            if event.result_date:
                date_text += f"; result date {event.result_date}"
            imgui.separator_text(f"{event.geography} — {date_text}")
            imgui.text_wrapped(
                f"{len(event.results)} reported result rows. {event.result_scope}",
                test_id=f"country.info.election_results.scope.{event_index}",
            )
            if event.source_name:
                imgui.text_wrapped(
                    f"Source organization: {event.source_name}",
                    test_id=f"country.info.election_results.source.{event_index}",
                )
            if event.source_reference:
                imgui.text_wrapped(
                    f"Source: {event.source_reference}",
                    test_id=f"country.info.election_results.reference.{event_index}",
                )
            if event.source_url:
                imgui.text_wrapped(
                    event.source_url,
                    test_id=f"country.info.election_results.url.{event_index}",
                )
            if event.source_note:
                imgui.text_wrapped(
                    event.source_note,
                    test_id=f"country.info.election_results.note.{event_index}",
                )
            for result_index, result in enumerate(event.results):
                values = []
                if result.votes is not None:
                    values.append(f"{result.votes:,} votes")
                if result.vote_share_pct is not None:
                    values.append(f"{result.vote_share_pct:.2f}%")
                if result.seats is not None:
                    seat_text = f"{result.seats} seats"
                    if result.general_seats is not None or result.special_seats is not None:
                        seat_parts = []
                        if result.general_seats is not None:
                            seat_parts.append(f"{result.general_seats} general")
                        if result.special_seats is not None:
                            seat_parts.append(f"{result.special_seats} special")
                        seat_text += f" ({', '.join(seat_parts)})"
                    values.append(seat_text)
                detail = ", ".join(values) if values else "no numeric result reported"
                imgui.text_wrapped(
                    f"{result.result_label} — {detail}",
                    test_id=(
                        f"country.info.election_results.entry.{event_index}."
                        f"{result_index}"
                    ),
                )

    @staticmethod
    def _party_roster_status_message(
        model: CountryMoreInfoModel,
        roster: PartyRosterContext2001,
    ) -> str:
        if roster.status == "party_field_not_reported":
            return (
                f"The 2001 Factbook has an entry for {roster.source_country or model.name}, "
                f"but it does not report the {SOURCE_PARTY_FIELD_2001} field."
            )
        if roster.status == "no_separate_country_entry":
            return (
                f"The 2001 Factbook has no separate country entry for {model.tag}; "
                "no party roster is inferred from a predecessor or another territory."
            )
        if roster.status == "field_without_named_party_record":
            return (
                "The source field is present, but it contains no individually named "
                "party or political organization records."
            )
        return "The historical party-roster coverage record is not loaded for this country."

    def _render_content(self, model: CountryMoreInfoModel) -> None:
        ui = GMLWidgets("Country_Information_Window/frmInner")
        # Child windows suspend the active GML slot mapper, so source frames are drawn on the parent canvas.
        for frame in (
            "frmLand",
            "frmHumanDevelopment",
            "frmPopulation",
            "frmTerrain",
            "frmClimate",
            "frmLand/frmMap",
            "frmHumanDevelopment/frmInner",
            "frmClimate/frmInner",
        ):
            self._draw_source_frame(ui, frame)
        self._render_land_frame(ui, model)
        self._render_human_development_frame(ui, model)
        self._render_population_frame(ui, model)
        self._render_terrain_frame(ui, model)
        self._render_climate_frame(ui, model)

    def _render_land_frame(self, ui: GMLWidgets, model: CountryMoreInfoModel) -> None:
        ui.picture(
            "frmLand/frmMap/frmMap",
            lambda width, height: self._draw_region_map(model, width, height),
        )
        for label_slot, meter_slot, value_slot, label, column in (
            ("lblArableLand", "frmArableLand", "txtArableLand", "Arable land", "arable_area_km2"),
            ("lblForests", "frmForests", "txtForests", "Forests", "forest_area_km2"),
            ("lblNationalParks", "frmNationalParks", "txtNationalParks", "Protected areas", "protected_area_km2"),
            ("lblUnusable", "frmUnusable", "txtUnusable", "Other land", "other_land_area_km2"),
        ):
            area = model.land_use_areas_km2.get(column)
            share = area / model.land_area_km2 if area is not None and model.land_area_km2 > 0 else None
            ui.text(f"frmLand/{label_slot}", label, test_id=f"country.info.land_cover.label.{value_slot}")
            ui.meter(f"frmLand/{meter_slot}", share if share is not None else 0.0, GAMETHEME.colors.info)
            ui.text(
                f"frmLand/{value_slot}", self._format_percent(share * 100) if share is not None else "—",
                tooltip="Share of the land in currently controlled regions."
                if share is not None else "Current land-use data is incomplete.",
                test_id=f"country.info.land_cover.{value_slot}",
            )

    def _render_human_development_frame(
        self, ui: GMLWidgets, model: CountryMoreInfoModel
    ) -> None:
        ui.text(
            "frmHumanDevelopment/lblTitle",
            "HUMAN DEVELOPMENT",
        )
        country_hdi = model.human_dev_pct / 100.0 if model.human_dev_pct is not None else None
        country_value = (
            self._format_percent(country_hdi * 100.0)
            if country_hdi is not None
            else "—"
        )
        world_value = (
            self._format_percent(model.world_human_dev_pct)
            if model.world_human_dev_pct is not None
            else "—"
        )
        ui.text(
            "frmHumanDevelopment/frmInner/lblCountry",
            f"{model.name}: {country_value}",
            test_id="country.info.hdi.country",
        )
        ui.meter(
            "frmHumanDevelopment/frmInner/picCountry",
            country_hdi if country_hdi is not None else 0.0,
            GAMETHEME.colors.positive,
        )
        ui.text(
            "frmHumanDevelopment/frmInner/lblWorld",
            f"World: {world_value}",
            tooltip="Arithmetic mean of available country development indices in the current simulation.",
            test_id="country.info.hdi.world",
        )
        ui.meter(
            "frmHumanDevelopment/frmInner/picWorld",
            model.world_human_dev_pct / 100.0
            if model.world_human_dev_pct is not None
            else 0.0,
            GAMETHEME.colors.warning,
        )
        draw_gml_separator(
            ui.path("frmHumanDevelopment/picSep"), color=GAMETHEME.colors.text_dim
        )
        ui.text("frmHumanDevelopment/lblInfrastructure", "Infrastructure")
        ui.text(
            "frmHumanDevelopment/txtInfrastructure",
            self._format_percent(model.infrastructure_pct),
            test_id="country.info.infrastructure.value",
        )
        ui.text("frmHumanDevelopment/lblTelecommunication", "Telecommunication")
        ui.text(
            "frmHumanDevelopment/txtTelecom",
            self._format_percent(model.telecom_pct),
            test_id="country.info.telecom.value",
        )

    def _render_population_frame(
        self, ui: GMLWidgets, model: CountryMoreInfoModel
    ) -> None:
        ui.text(
            "frmPopulation/lblTitle",
            "POPULATION",
        )
        fields = (
            ("lbl15", "txt15", "txt15Ratio", model.population_bands[0], "0–14"),
            ("lbl1565", "txt1565", "txt1565Ratio", model.population_bands[1], "15–64"),
            ("lbl65", "txt65", "txt65Ratio", model.population_bands[2], "65+"),
        )
        for label_slot, value_slot, ratio_slot, band, label in fields:
            ui.text(f"frmPopulation/{label_slot}", label)
            ui.text(
                f"frmPopulation/{value_slot}",
                self._format_population_value(model, band.value),
                test_id=f"country.info.population.{label}.value",
            )
            ui.text(
                f"frmPopulation/{ratio_slot}",
                f"{band.percent:.1f} %" if model.population_available else "—",
            )

        ui.text("frmPopulation/lblTotal", "Total")
        ui.text(
            "frmPopulation/txtTotal",
            self._format_population_value(model, model.population_total),
            test_id="country.info.population.total",
        )
        ui.text(
            "frmPopulation/txtTotalRatio",
            "100.0 %" if model.population_available else "—",
        )
        draw_gml_separator(
            ui.path("frmPopulation/picSep"), color=GAMETHEME.colors.text_dim
        )
        for widget, label, event, rate in (
            ("BirthRate", "Birth rate", "births", model.birth_rate_per_1000),
            ("DeathRate", "Death rate", "deaths", model.death_rate_per_1000),
        ):
            ui.text(f"frmPopulation/lbl{widget}", label)
            ui.text(
                f"frmPopulation/txt{widget}",
                f"{rate:.1f} ‰" if rate is not None else "—",
                tooltip=(
                    f"Modeled {event} per year per 1,000 residents."
                    if rate is not None else f"Current {label.lower()} data is unavailable."
                ),
                test_id=f"country.info.{label.lower().replace(' ', '_')}.value",
            )

    def _render_terrain_frame(
        self, ui: GMLWidgets, model: CountryMoreInfoModel
    ) -> None:
        ui.text("frmTerrain/lblTitle", "TERRAIN")
        ui.text("frmTerrain/lblLandArea", "Land area (km²)")
        ui.text(
            "frmTerrain/txtLandArea",
            self._format_int(model.land_area_km2) if model.land_area_available else "—",
            tooltip=(
                f"Controlled regions: {model.region_count}; world land share: {model.world_area_share_pct:.2f}%; "
                f"density: {model.density_per_km2:.1f} residents/km². {model.region_summary} "
                f"Age composition: {self._row_summary(model.population_bands, 'value')}. "
                f"Region composition by land: {self._row_summary(model.composition_rows)}. "
                f"Leading production sectors: {self._row_summary(model.production_rows)}."
            ),
            test_id="country.info.land_area.value",
        )
        ui.text("frmTerrain/lblWaterArea", "Water area (km²)")
        ui.text(
            "frmTerrain/txtWaterArea",
            self._format_int(model.inland_water_area_km2) if model.inland_water_area_km2 is not None else "—",
            tooltip="Inland water across currently controlled regions.",
            test_id="country.info.water_area.value",
        )
        ui.text("frmTerrain/lblTotalArea", "Total area (km²)")
        ui.text(
            "frmTerrain/txtTotalArea",
            self._format_int(model.land_area_km2 + model.inland_water_area_km2)
            if model.land_area_available and model.inland_water_area_km2 is not None else "—",
            tooltip="Land and inland water across currently controlled regions.",
            test_id="country.info.total_area.value",
        )

    def _render_climate_frame(
        self, ui: GMLWidgets, model: CountryMoreInfoModel | None = None
    ) -> None:
        ui.text("frmClimate/lblTitle", "CLIMATE")
        ui.text(
            "frmClimate/frmInner/lblClimate",
            "—",
            tooltip="Current climate data is unavailable.",
            test_id="country.info.climate.value",
        )

    @staticmethod
    def _historical_provenance(model: CountryMoreInfoModel, field: str) -> dict:
        raw = model.historical_metrics.get("historical_metric_provenance_json")
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        record = data.get(field)
        return record if isinstance(record, dict) else {}

    @staticmethod
    def _land_metric_tooltip(model: CountryMoreInfoModel, field: str) -> str:
        provenance = CountryMoreInfoPanel._historical_provenance(model, field)
        if not provenance:
            return "Historical land metric for the 2001 scenario; source details unavailable."
        source = safe_text(provenance.get("source"), "historical source")
        observation_year = provenance.get("observation_year")
        source_year = provenance.get("source_year")
        source_scope = safe_text(provenance.get("source_scope"))
        source_note = safe_text(provenance.get("source_note"))
        source_url = safe_text(provenance.get("url"))
        details = [f"{source}; observation year {observation_year or 'unspecified'}."]
        if source_scope:
            details.append(f"Source scope: {source_scope}.")
        if source_note:
            details.append(source_note)
        if source_year and str(source_year) != str(observation_year):
            details.append(f"Source publication or release year: {source_year}.")
        if source_url:
            details.append(f"Source: {source_url}")
        return " ".join(details)

    @staticmethod
    def _climate_context_tooltip(model: CountryMoreInfoModel) -> str:
        provenance = CountryMoreInfoPanel._historical_provenance(
            model, "climate_description"
        )
        if not provenance:
            return "Historical climate context for the 2001 scenario; source details unavailable."

        source = safe_text(provenance.get("source"), "historical source")
        source_year = provenance.get("source_year")
        source_scope = safe_text(provenance.get("source_scope"))
        source_note = safe_text(provenance.get("source_note"))
        source_url = safe_text(provenance.get("url"))
        proxy = "proxy" in source_scope.lower() or "proxy" in source_note.lower()
        if proxy:
            prefix = "Historical climate context uses a territory or regional proxy."
        elif source == "CIA Factbook 2001":
            prefix = "Historical climate context from a direct country entry in the 2001 CIA Factbook."
        else:
            prefix = (
                "Historical climate context from a source describing this territory."
            )
        details = [prefix]
        if source_scope:
            details.append(f"Source scope: {source_scope}.")
        details.append(source_note or f"Source: {source}.")
        if source_year:
            details.append(f"Source document/edition year: {source_year}.")
        if source_url:
            details.append(f"Source: {source_url}")
        return " ".join(details)

    @staticmethod
    def _historical_value(model: CountryMoreInfoModel, key: str) -> float | None:
        row = model.historical_metrics
        # The loader normalizes numeric nulls to zero; preserve explicit source availability.
        availability = row.get(f"{key}_available")
        if availability is None and key.endswith("_pct"):
            availability = row.get(f"{key[:-4]}_available")
        if availability in (False, "False", "false", 0):
            # Missing source values are normalized to zero by the loader, so
            # consult the separate country-specific scenario values instead.
            raw = row.get("countryinfo_scenario_values_2001_json")
            try:
                estimates = json.loads(raw) if isinstance(raw, str) else raw
            except (TypeError, ValueError):
                return None
            value = estimates.get(key) if isinstance(estimates, dict) else None
            if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value):
                return float(value)
            return None
        value = row.get(key)
        return safe_float(value) if value is not None else None

    @staticmethod
    def _other_land_display_value(
        model: CountryMoreInfoModel,
        direct_value: float | None,
        direct_label: str,
    ) -> tuple[float | None, str]:
        if direct_value is not None:
            return direct_value, direct_label
        estimate = CountryMoreInfoPanel._historical_value(
            model, "scenario_other_land_2001_pct"
        )
        return (
            (estimate, "Other land estimate")
            if estimate is not None
            else (None, direct_label)
        )

    @staticmethod
    def _other_land_tooltip(model: CountryMoreInfoModel) -> str:
        row = model.historical_metrics
        lines: list[str] = []
        direct_value = CountryMoreInfoPanel._historical_value(model, "other_land_pct")
        if direct_value is not None:
            flag = safe_text(row.get("other_land_source_flag"), "unavailable")
            description = safe_text(
                row.get("other_land_source_flag_description"),
                "source quality flag unavailable",
            )
            lines.append(
                f"{OTHER_LAND_SOURCE_TOOLTIP} FAOSTAT quality flag {flag}: {description}. "
                "Source: https://www.fao.org/faostat/en/#data/RL"
            )
        else:
            estimate = CountryMoreInfoPanel._historical_value(
                model, "scenario_other_land_2001_pct"
            )
            if estimate is not None:
                area = safe_text(row.get("scenario_other_land_2001_area_ha"), "unknown")
                period = safe_text(
                    row.get("scenario_other_land_2001_reference_period"),
                    "unspecified period",
                )
                method = safe_text(
                    row.get("scenario_other_land_2001_method"),
                    "residual estimate",
                )
                quality = safe_text(
                    row.get("scenario_other_land_2001_quality"),
                    "unspecified",
                )
                source_flag = safe_text(
                    row.get("scenario_other_land_2001_source_flag"),
                    "unavailable",
                )
                scope = safe_text(
                    row.get("scenario_other_land_2001_scope"),
                    "country scope unavailable",
                )
                note = safe_text(
                    row.get("scenario_other_land_2001_source_note"), ""
                )
                urls = safe_text(
                    row.get("scenario_other_land_2001_source_urls"), ""
                )
                lines.append(
                    f"Low-confidence Other land scenario estimate for 2001: "
                    f"{area} ha; {estimate:.4f}% of the source land-area denominator. "
                    f"Reference period: {period}. Method: {method}. Quality: {quality}; "
                    f"FAOSTAT source flag: {source_flag}. Scope: {scope}."
                )
                if note:
                    lines.append(note)
                if urls:
                    lines.append(f"Sources: {urls}")
            else:
                lines.append(
                    f"{OTHER_LAND_SOURCE_TOOLTIP} No FAOSTAT-compatible observation or "
                    "scenario estimate is available for this country."
                )

        cia_alternative = CountryMoreInfoPanel._historical_value(
            model, "scenario_cia_land_use_other_2001_pct"
        )
        if cia_alternative is not None:
            cia_scope = safe_text(
                row.get("scenario_cia_land_use_other_2001_scope"),
                "CIA Factbook scope",
            )
            cia_note = safe_text(
                row.get("scenario_cia_land_use_other_2001_source_note"), ""
            )
            cia_url = safe_text(
                row.get("scenario_cia_land_use_other_2001_source_url"), ""
            )
            lines.append(
                f"Separate CIA Factbook 2001 `other` category: {cia_alternative:.4f}%. "
                f"This definition is not comparable to FAOSTAT Other land. Scope: {cia_scope}."
            )
            if cia_note:
                lines.append(cia_note)
            if cia_url:
                lines.append(f"CIA source: {cia_url}")

        return " ".join(lines)

    @staticmethod
    def _palestinian_reserve_context(row: dict) -> list[str]:
        observations: list[str] = []
        for year in ("2000", "2001"):
            value_key = f"countryinfo_pna_west_bank_natural_reserves_{year}_area_km2"
            available_key = f"{value_key}_available"
            if str(row.get(available_key, "")).strip().lower() not in {
                "true",
                "1",
                "yes",
            }:
                continue
            value = safe_float(row.get(value_key), 0.0)
            precision = safe_text(
                row.get(f"{value_key}_precision"), "reported"
            )
            period = safe_text(
                row.get(f"{value_key}_reported_period"), year
            )
            source_name = safe_text(
                row.get(f"{value_key}_source_name"),
                "Palestinian Central Bureau of Statistics",
            )
            source_url = safe_text(row.get(f"{value_key}_source_url"), "")
            source_location = safe_text(
                row.get(f"{value_key}_source_location"), "source table unavailable"
            )
            scope = safe_text(
                row.get(f"{value_key}_geographic_scope"), "West Bank"
            )
            coverage_limit = safe_text(
                row.get(f"{value_key}_coverage_limit"), "coverage is incomplete"
            )
            handling_note = safe_text(
                row.get(f"{value_key}_handling_note"), ""
            )
            approximate = "about " if precision == "approximate" else ""
            observations.append(
                f"Separate PNA-controlled natural-reserves context, {year}: "
                f"{approximate}{value:g} km²; source scope: {scope}; {period}. "
                f"This is not a national-park value or a complete national protected-area total. "
                f"Coverage limit: {coverage_limit}. Source: {source_name}, {source_location}."
            )
            if handling_note:
                observations.append(handling_note)
            if source_url:
                observations.append(f"Source URL: {source_url}")
        return observations

    @staticmethod
    def _protected_area_tooltip(model: CountryMoreInfoModel) -> str:
        row = model.historical_metrics
        source = safe_text(row.get("terrestrial_protected_area_source"), "")
        method = safe_text(row.get("terrestrial_protected_area_method"), "")
        source_url = safe_text(row.get("terrestrial_protected_area_source_url"), "")
        if source.startswith("Maldives Ministry"):
            park_coverage = CountryMoreInfoPanel._historical_value(
                model, "national_park_land_coverage_pct_2001"
            )
            park_text = (
                f" The separate terrestrial national-park share for 2001 is {park_coverage:.4f}%."
                if park_coverage is not None
                else ""
            )
            return (
                f"Derived 2000 terrestrial protected-area share from {source}: {method} "
                f"This is not a direct UNSD observation.{park_text} Source: {source_url}"
            )
        if source.startswith("UNSD"):
            result = PROTECTED_AREA_SOURCE_TOOLTIP
            if safe_text(row.get("id"), "").upper() == "PSE":
                result += " " + " ".join(
                    CountryMoreInfoPanel._palestinian_reserve_context(row)
                )
            return result
        protected_area = CountryMoreInfoPanel._historical_value(
            model, "terrestrial_protected_area_pct_2000"
        )
        if protected_area is not None and source:
            details = [
                f"Reported 2000 terrestrial protected-area share: {protected_area:.1f}%.",
                method,
                f"Source: {source}.",
            ]
            if source_url:
                details.append(source_url)
            return " ".join(
                [detail for detail in details if detail]
                + (
                    CountryMoreInfoPanel._palestinian_reserve_context(row)
                    if safe_text(row.get("id"), "").upper() == "PSE"
                    else []
                )
            )
        if protected_area is not None and row.get("terrestrial_protected_area_pct_2000_available") in (False, "False", "false", 0):
            result = f"Terrestrial protected area: {protected_area:.1f}%."
            if safe_text(row.get("id"), "").upper() == "PSE":
                result += " " + " ".join(
                    CountryMoreInfoPanel._palestinian_reserve_context(row)
                )
            return result
        status = safe_text(row.get("national_park_status"), "")
        notes = safe_text(row.get("national_park_notes"), "")
        if status or notes:
            result = (
                "No comparable 2000 all-category terrestrial protected-area share is available. "
                f"National-park evidence status: {status or 'unavailable'}. {notes}"
            )
        else:
            result = (
                f"{PROTECTED_AREA_SOURCE_TOOLTIP} "
                "No matching 2000 observation is available for this country."
            )
        if safe_text(row.get("id"), "").upper() == "PSE":
            result += " " + " ".join(
                CountryMoreInfoPanel._palestinian_reserve_context(row)
            )
        return result

    @staticmethod
    def _national_park_tooltip(model: CountryMoreInfoModel) -> str:
        row = model.historical_metrics
        area = CountryMoreInfoPanel._historical_value(
            model, "national_park_land_area_km2_2001"
        )
        coverage = CountryMoreInfoPanel._historical_value(
            model, "national_park_land_coverage_pct_2001"
        )
        status = safe_text(row.get("national_park_status"), "documented estimate")
        notes = safe_text(row.get("national_park_notes"), "")
        source = safe_text(
            row.get("national_park_source_url"), "source URL unavailable"
        )
        denominator = safe_text(row.get("national_park_denominator_source_url"), "")
        value_text = (
            f"{area:.2f} km²; {coverage:.4f}% of land area. "
            if area is not None and coverage is not None
            else ""
        )
        denominator_text = f" Denominator source: {denominator}." if denominator else ""
        return (
            f"National-park land coverage for the 2001 scenario ({status}): {value_text}{notes} "
            f"Source: {source}.{denominator_text} This park-only measure is not the broader UNSD protected-area share."
        )

    def _historical_rate(self, model: CountryMoreInfoModel, key: str) -> str:
        value = self._historical_value(model, key)
        return f"{value:.2f} ‰" if value is not None else "—"

    def _historical_area(self, model: CountryMoreInfoModel, key: str) -> str:
        value = self._historical_value(model, key)
        return self._format_int(value) if value is not None else "—"

    def _historical_area_tooltip(self, model: CountryMoreInfoModel, key: str) -> str:
        value = self._historical_value(model, key)
        if value is None:
            return (
                "No sourced historical area observation is available for this country."
            )

        provenance = self._historical_provenance(model, key)
        source = safe_text(provenance.get("source"), "source unspecified")
        observation_year = provenance.get("observation_year")
        year_label = (
            str(int(observation_year)) if observation_year is not None else "not stated"
        )
        source_year = provenance.get("source_year")
        scope = safe_text(provenance.get("source_scope"), "country-level row")
        note = safe_text(provenance.get("source_note"), "")
        url = safe_text(provenance.get("url"), "")
        label = (
            "inland-water area"
            if key == "reference_water_area_km2"
            else "total surface area"
        )
        details = [
            f"Historical national {label}: {self._format_int(value)} km² "
            f"(observation year {year_label}; source {source}; scope {scope})"
        ]
        if source_year:
            details.append(f"Source edition year: {source_year}.")
        if note:
            details.append(note)
        if url:
            details.append(f"Source: {url}")

        if key in {"reference_water_area_km2", "reference_total_area_km2"}:
            water = self._historical_value(model, "reference_water_area_km2")
            land = self._historical_value(model, "reference_land_area_km2")
            total = self._historical_value(model, "reference_total_area_km2")
            water_provenance = self._historical_provenance(
                model, "reference_water_area_km2"
            )
            land_provenance = self._historical_provenance(
                model, "reference_land_area_km2"
            )
            total_provenance = self._historical_provenance(
                model, "reference_total_area_km2"
            )
            if (
                water is not None
                and water_provenance.get("source") == "CIA Factbook 2001"
                and land is not None
                and total is not None
                and land_provenance.get("source") == "AG.LND.TOTL.K2"
                and total_provenance.get("source") == "AG.SRF.TOTL.K2"
                and land_provenance.get("observation_year") == HISTORICAL_REFERENCE_YEAR
                and total_provenance.get("observation_year")
                == HISTORICAL_REFERENCE_YEAR
            ):
                calculated_water = total - land
                difference = calculated_water - water
                if abs(difference) >= 0.5:
                    if key == "reference_water_area_km2":
                        details.append(
                            "Source difference: World Bank WDI 2001 total surface "
                            f"({self._format_int(total)} km²) minus WDI 2001 land "
                            f"({self._format_int(land)} km²) implies "
                            f"{self._format_int(calculated_water)} km² of water, while "
                            f"the direct CIA Factbook value is {self._format_int(water)} km². "
                            "These source series do not reconcile; the displayed CIA value "
                            "is retained without substitution."
                        )
                    else:
                        details.append(
                            "Related water-area source difference: WDI 2001 total "
                            f"surface minus WDI 2001 land implies "
                            f"{self._format_int(calculated_water)} km² of water, while "
                            f"the direct CIA Factbook value is {self._format_int(water)} km² "
                            "(estimate year not stated). The values do not reconcile; both "
                            "source records are preserved."
                        )
        details.append(
            "Historical national areas describe the 2001 country record and do not "
            "change with territory controlled in the simulation."
        )
        return " ".join(details)

    @staticmethod
    def _row_summary(rows, value_key: str = "value") -> str:
        if not rows:
            return "unavailable"
        return "; ".join(
            f"{row.label}: {row.percent:.1f}% ({getattr(row, value_key)})"
            for row in rows
        )

    def _historical_demographics_tooltip(self, model: CountryMoreInfoModel) -> str:
        details = []
        for key, label, units in (
            ("fertility_rate", "fertility", "children/woman"),
            ("life_expectancy", "life expectancy", "years"),
        ):
            value = self._historical_value(model, key)
            if value is not None:
                details.append(f"{label}: {value:.2f} {units}")
        poverty = self._historical_value(model, "historical_poverty_rate_pct")
        poverty_year = self._historical_value(model, "historical_poverty_rate_year")
        if poverty is not None:
            provenance = self._historical_provenance(
                model, "historical_poverty_rate_pct"
            )
            observation_year = provenance.get("observation_year") or poverty_year
            estimate_year = (
                int(observation_year) if observation_year else "year unspecified"
            )
            source = safe_text(provenance.get("source"), "source unspecified")
            source_year = provenance.get("source_year")
            if source == "SI.POV.NAHC":
                source_label = "World Bank WDI SI.POV.NAHC"
            else:
                source_label = (
                    f"{source}, source year {source_year}" if source_year else source
                )
            details.append(
                f"poverty estimate: {poverty:.1f}% (observation year {estimate_year}; {source_label})"
            )
            if source == "SI.POV.NAHC":
                details.append(
                    "national poverty-line values are country-specific and not cross-country comparable"
                )
        national_poverty = self._historical_value(
            model, "historical_national_poverty_supplement_pct"
        )
        national_poverty_available = model.historical_metrics.get(
            "historical_national_poverty_supplement_available"
        )
        if national_poverty is not None and national_poverty_available is not False:
            row = model.historical_metrics
            observation_year = safe_text(
                row.get("historical_national_poverty_supplement_reference_year"),
                "year unspecified",
            )
            survey_period = safe_text(
                row.get("historical_national_poverty_supplement_survey_period"),
                "survey period unspecified",
            )
            line = safe_text(
                row.get("historical_national_poverty_supplement_line_definition"),
                "national poverty line definition unavailable",
            )
            welfare = safe_text(
                row.get("historical_national_poverty_supplement_welfare_measure"),
                "welfare measure unavailable",
            )
            scope = safe_text(
                row.get("historical_national_poverty_supplement_scope"),
                "population scope unavailable",
            )
            method = safe_text(
                row.get("historical_national_poverty_supplement_method"), ""
            )
            source = safe_text(
                row.get("historical_national_poverty_supplement_source"),
                "source unspecified",
            )
            source_url = safe_text(
                row.get("historical_national_poverty_supplement_source_url"), ""
            )
            source_note = safe_text(
                row.get("historical_national_poverty_supplement_source_note"), ""
            )
            detail = (
                f"National poverty-line alternative: {national_poverty:.1f}% "
                f"(observation year {observation_year}; survey period {survey_period}; "
                f"{source}). {line} Welfare: {welfare}. Scope: {scope}."
            )
            if method:
                detail += f" Method: {method}."
            if source_note:
                detail += f" {source_note}"
            if source_url:
                detail += f" Source: {source_url}"
            details.append(detail)
        pip_headcount = self._historical_value(
            model, "historical_poverty_global_3usd_2021_ppp_pct"
        )
        if pip_headcount is None:
            unavailable_note = safe_text(
                model.historical_metrics.get(
                    "historical_poverty_global_3usd_2021_ppp_unavailable_note"
                ),
                "no exact-year national survey record available",
            )
            details.append(
                "PIP $3/day (2021 PPP) poverty headcount: unavailable "
                f"({unavailable_note})"
            )
        else:
            row = model.historical_metrics
            pip_survey_year = self._historical_value(
                model,
                "historical_poverty_global_3usd_2021_ppp_pct_survey_year",
            )
            survey_year = (
                f"{pip_survey_year:.2f}" if pip_survey_year is not None else "2001"
            )
            welfare_type = safe_text(
                row.get("historical_poverty_global_3usd_2021_ppp_pct_welfare_type"),
                "income or consumption",
            )
            survey = safe_text(
                row.get("historical_poverty_global_3usd_2021_ppp_pct_survey_acronym"),
                "survey name unavailable",
            )
            population_scope = safe_text(
                row.get("historical_poverty_global_3usd_2021_ppp_pct_population_scope"),
                "population age scope unavailable",
            )
            details.append(
                f"PIP $3/day (2021 PPP) poverty headcount: {pip_headcount:.2f}% "
                f"(survey year {survey_year}; {welfare_type}; {survey}; "
                f"{population_scope})"
            )
            alternate = self._historical_value(
                model,
                "historical_poverty_global_3usd_2021_ppp_pct_alternate",
            )
            if alternate is not None:
                alternate_welfare = safe_text(
                    row.get(
                        "historical_poverty_global_3usd_2021_ppp_pct_alternate_welfare_type"
                    ),
                    "alternate welfare measure",
                )
                details.append(
                    f"PIP also reports {alternate:.2f}% from the same survey using {alternate_welfare}"
                )
            pip_url = safe_text(
                row.get("historical_poverty_global_3usd_2021_ppp_pct_source_url"),
                "",
            )
            if pip_url:
                details.append(
                    "Retrospective PIP estimate using a 2021 PPP line; it is separate from the country-specific national poverty line and was not published as a $3 line in 2001. "
                    f"Source: {pip_url}"
                )
        model_value_key = "gameplay_poverty_estimate_3usd_2021_ppp_pct"
        model_estimate = self._historical_value(model, model_value_key)
        model_type = safe_text(
            model.historical_metrics.get(
                "gameplay_poverty_estimate_3usd_2021_ppp_type"
            ),
            "",
        )
        if model_estimate is not None and model_type == "gameplay_model":
            row = model.historical_metrics
            confidence = safe_text(
                row.get("gameplay_poverty_estimate_3usd_2021_ppp_confidence"),
                "unknown",
            )
            method = safe_text(
                row.get("gameplay_poverty_estimate_3usd_2021_ppp_method"),
                "method unavailable",
            )
            training_count = safe_text(
                row.get(
                    "gameplay_poverty_estimate_3usd_2021_ppp_training_observation_count"
                ),
                "unknown",
            )
            nearest_ids = safe_text(
                row.get("gameplay_poverty_estimate_3usd_2021_ppp_nearest_training_ids"),
                "unavailable",
            )
            hdi_input = safe_text(
                row.get("gameplay_poverty_estimate_3usd_2021_ppp_hdi_input_2001"),
                "unavailable",
            )
            hdi_quality = safe_text(
                row.get("gameplay_poverty_estimate_3usd_2021_ppp_hdi_input_quality"),
                "unknown quality",
            )
            gni_input = safe_text(
                row.get(
                    "gameplay_poverty_estimate_3usd_2021_ppp_gni_per_capita_ppp_current_intl_dollars_2001"
                ),
                "unavailable",
            )
            details.append(
                "OpenPower gameplay estimate for the PIP $3/day (2021 PPP) international line: "
                f"{model_estimate:.2f}% (confidence {confidence}; not a survey result or national-line estimate)."
            )
            details.append(
                f"Model: {method} Training observations: {training_count}; nearest source records: {nearest_ids}; "
                f"2001 HDI input: {hdi_input} ({hdi_quality}); 2001 GNI per capita PPP input: {gni_input}."
            )
            model_note = safe_text(
                row.get("gameplay_poverty_estimate_3usd_2021_ppp_source_note"), ""
            )
            if model_note:
                details.append(model_note)
            model_sources = safe_text(
                row.get("gameplay_poverty_estimate_3usd_2021_ppp_source_urls"), ""
            )
            if model_sources:
                details.append(f"Model input sources: {model_sources}")
        elif model_type == "not_estimated":
            model_note = safe_text(
                model.historical_metrics.get(
                    "gameplay_poverty_estimate_3usd_2021_ppp_source_note"
                ),
                "no usable historical HDI input was available",
            )
            details.append(
                "OpenPower gameplay estimate for the PIP $3/day (2021 PPP) line: unavailable "
                f"({model_note})"
            )
        prefix = "Birth/death rates are per 1,000 residents; sourced observations are dated 2001."
        return f"{prefix} " + (
            "; ".join(details)
            if details
            else "Additional historical demographic observations unavailable."
        )

    @staticmethod
    def _development_supplement_tooltip(model: CountryMoreInfoModel) -> str:
        row = model.historical_metrics
        observations = (
            (
                "historical_school_life_expectancy_wdi_years_2001",
                "School life expectancy (years)",
                2,
            ),
            (
                "historical_gni_per_capita_wdi_ppp_current_intl_dollars_2001",
                "GNI per capita (current international dollars)",
                0,
            ),
            (
                "historical_mean_schooling_barrolee_years_population_15plus_2000",
                "Mean schooling, ages 15+ (years)",
                2,
            ),
            (
                "historical_mean_schooling_barrolee_years_population_25plus_2000",
                "Mean schooling, ages 25+ (years)",
                2,
            ),
        )
        details = []
        for metric_key, label, precision in observations:
            value = CountryMoreInfoPanel._historical_value(model, metric_key)
            if value is None:
                continue
            observation_year = CountryMoreInfoPanel._historical_value(
                model, f"{metric_key}_observation_year"
            )
            year = (
                int(observation_year) if observation_year is not None else "unspecified"
            )
            source = safe_text(row.get(f"{metric_key}_source"), "source unspecified")
            scope = safe_text(
                row.get(f"{metric_key}_source_scope"), "scope unspecified"
            )
            note = safe_text(row.get(f"{metric_key}_source_note"), "")
            url = safe_text(row.get(f"{metric_key}_source_url"), "")
            formatted_value = f"{value:,.{precision}f}"
            detail = f"{label}: {formatted_value} (observation year {year}; {source}; {scope})"
            if note:
                detail += f" {note}"
            if url:
                detail += f" Source: {url}"
            details.append(detail)
        if not details:
            return (
                "UNDP country HDI is the displayed historical development measure. "
                "No separate WDI or Barro-Lee education/income supplement is available for this country."
            )
        return (
            "Dated supplementary education and income observations, displayed separately from the UNDP country HDI: "
            + "; ".join(details)
        )

    @staticmethod
    def _country_hdi_tooltip(model: CountryMoreInfoModel) -> str:
        row = model.historical_metrics
        status = safe_text(row.get("reference_human_dev_status"), "unavailable")
        method = safe_text(row.get("reference_human_dev_method"), "")
        source = safe_text(row.get("reference_human_dev_source"), "")
        source_url = safe_text(row.get("reference_human_dev_source_url"), "")
        if status == "official_undp_hdr2025":
            return "UNDP HDR 2025 retrospective country HDI, observation year 2001; historical baseline."
        if status == "official_legacy_method":
            return (
                f"{method} This is an official 2001 observation using the older HDR 2003 method and is not "
                f"directly comparable with HDR 2025 values. Source: {source}. {source_url}"
            )
        if status == "calculated_estimate":
            return f"Estimated 2001 HDI; not published by UNDP. {method} Source: {source}. {source_url}"
        if status in {
            "regional_estimate_proxy",
            "national_report_proxy",
            "territory_proxy",
        }:
            return f"Historical HDI proxy, not a comparable UNDP 2001 country observation. {method} Source: {source}. {source_url}"
        if status in {"not_applicable", "not_reported"}:
            if CountryMoreInfoPanel._historical_value(model, "reference_human_dev") is not None:
                return "Human development index for 2001."
            return f"No historical country HDI is available. {method} The simulation uses a neutral 0.50 fallback, which is not displayed as an HDI."
        return "No historical HDI value or source classification is available."

    def _draw_source_frame(self, ui: GMLWidgets, slot: str) -> None:
        session = active_gml_layout()
        rect = ui.rect(slot)
        if session is None or rect is None:
            return

        x = session.window_position[0] + rect.x - imgui.get_scroll_x()
        y = session.window_position[1] + rect.y - imgui.get_scroll_y()
        draw_list = imgui.get_window_draw_list()
        minimum = (x, y)
        maximum = (x + rect.width, y + rect.height)
        draw_list.add_rect_filled(
            minimum,
            maximum,
            imgui.get_color_u32(GAMETHEME.colors.panel_bg_dark),
        )
        draw_list.add_rect(
            minimum,
            maximum,
            imgui.get_color_u32((0.3, 0.3, 0.3, 0.55)),
            0.0,
            flags=0,
            thickness=1.0,
        )

    def _draw_region_map(
        self, model: CountryMoreInfoModel, frame_w: float, frame_h: float
    ) -> None:
        p = imgui.get_cursor_screen_pos()
        draw_list = imgui.get_window_draw_list()
        draw_list.add_rect_filled(
            p,
            (p.x + frame_w, p.y + frame_h),
            imgui.get_color_u32((0.03, 0.035, 0.04, 1.0)),
        )
        draw_list.add_rect(
            p,
            (p.x + frame_w, p.y + frame_h),
            imgui.get_color_u32((0.24, 0.52, 0.70, 0.95)),
            0.0,
            flags=0,
            thickness=1.5,
        )

        map_data = self._map_data_provider()
        texture = self._map_textures.get_texture(map_data, model.region_ids)
        if texture is None:
            self._render_map_placeholder(p, frame_w, frame_h)
            return

        draw_w, draw_h = self._fit_texture(texture, frame_w - 14.0, frame_h - 14.0)
        draw_x = p.x + (frame_w - draw_w) * 0.5
        draw_y = p.y + (frame_h - draw_h) * 0.5
        imgui.set_cursor_screen_pos((draw_x, draw_y))
        self._map_textures.draw_texture(
            texture, draw_w, draw_h, test_id="country.info.region_map"
        )
        imgui.set_cursor_screen_pos((p.x, p.y))

    def _render_map_placeholder(self, origin, width: float, height: float) -> None:
        text = "No region map"
        text_size = imgui.calc_text_size(text)
        imgui.set_cursor_screen_pos(
            (
                origin.x + (width - text_size.x) * 0.5,
                origin.y + (height - text_size.y) * 0.5,
            )
        )
        imgui.text_disabled(text)

    def _fit_texture(
        self, texture: CountryMapTexture, max_w: float, max_h: float
    ) -> tuple[float, float]:
        if texture.width <= 0 or texture.height <= 0:
            return max_w, max_h
        scale = min(max_w / texture.width, max_h / texture.height)
        return texture.width * scale, texture.height * scale

    def _format_int(self, value: float | int) -> str:
        return f"{int(round(float(value))):,}".replace(",", " ")

    def _format_percent(self, value: float) -> str:
        return f"{value:.1f} %"

    def _format_population_value(self, model: CountryMoreInfoModel, value: int) -> str:
        return self._format_int(value) if model.population_available else "—"
