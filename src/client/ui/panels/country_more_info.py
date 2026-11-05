from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import polars as pl
from src.client.ui.core.instrumented_imgui import imgui

from src.client.renderers.country_region_map import CountryMapTexture, CountryRegionMapTextureCache
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.gml_layout import (
    active_gml_layout,
    draw_gml_separator,
    get_gml_layout,
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
    human_dev_pct: float
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


class CountryMoreInfoPresenter:
    """Builds a country info view model from data-oriented game tables."""

    def build(self, state, country_tag: str) -> CountryMoreInfoModel:
        tag = safe_text(country_tag, "Unknown")
        country_row = get_country_row(state, tag)
        country_regions = self._country_regions(state, tag)

        region_ids = self._region_ids(country_regions)
        population_bands = self._population_bands(country_regions)
        population_total = sum(band.value for band in population_bands)
        land_area = self._sum_column(country_regions, "area_km2")
        world_area = self._sum_column(getattr(state, "tables", {}).get("regions"), "area_km2")
        population_available = (
            not country_regions.is_empty()
            and {"pop_14", "pop_15_64", "pop_65"}.issubset(country_regions.columns)
        )
        land_area_available = not country_regions.is_empty() and "area_km2" in country_regions.columns

        return CountryMoreInfoModel(
            tag=tag,
            name=resolve_country_name(state, tag),
            region_ids=region_ids,
            region_count=len(region_ids),
            land_area_km2=land_area,
            world_area_share_pct=(land_area / world_area * 100.0) if world_area > 0 else 0.0,
            population_total=population_total,
            population_bands=population_bands,
            population_available=population_available,
            density_per_km2=(population_total / land_area) if land_area > 0 else 0.0,
            human_dev_pct=as_percent(country_row.get("human_dev")),
            # Averaging country HDI values would invent semantics for the missing world-level indicator.
            # Source formula: GDataControlLayer::AverageHumanDevelopment.
            world_human_dev_pct=None,
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
        return tuple(int(value) for value in regions["id"].drop_nulls().to_list() if int(value) > 0)

    def _population_bands(self, regions: pl.DataFrame) -> tuple[PopulationBand, ...]:
        values = (
            ("0-14 years", safe_int(self._sum_column(regions, "pop_14"))),
            ("15-65 years", safe_int(self._sum_column(regions, "pop_15_64"))),
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

        group_col = "type" if "type" in regions.columns else "macro_region" if "macro_region" in regions.columns else ""
        if not group_col:
            return ()

        weight_col = "area_km2" if "area_km2" in regions.columns else ""
        try:
            if weight_col:
                grouped = (
                    regions
                    .group_by(group_col)
                    .agg(pl.col(weight_col).sum().alias("weight"), pl.len().alias("count"))
                    .sort("weight", descending=True)
                )
                total = float(grouped["weight"].sum() or 0.0)
            else:
                grouped = regions.group_by(group_col).agg(pl.len().alias("count")).sort("count", descending=True)
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
                production
                .filter(pl.col("country_id") == tag)
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
                    label=safe_text(row.get("game_resource_id"), "Unknown").replace("_", " ").title(),
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
    def __init__(self, map_data_provider: Callable[[], RegionMapData | None] | None = None):
        self._presenter = CountryMoreInfoPresenter()
        self._map_textures = CountryRegionMapTextureCache()
        self._map_data_provider = map_data_provider or (lambda: None)

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
                return False

            self._render_content(model)
            return True

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
        self._render_climate_frame(ui)

    def _render_land_frame(self, ui: GMLWidgets, model: CountryMoreInfoModel) -> None:
        ui.picture(
            "frmLand/frmMap/frmMap",
            lambda width, height: self._draw_region_map(model, width, height),
        )
        for label_slot, meter_slot, value_slot, label in (
            ("lblArableLand", "frmArableLand", "txtArableLand", "Arable land"),
            ("lblForests", "frmForests", "txtForests", "Forests"),
            ("lblNationalParks", "frmNationalParks", "txtNationalParks", "National parks"),
            ("lblUnusable", "frmUnusable", "txtUnusable", "Unusable land"),
        ):
            ui.text(f"frmLand/{label_slot}", label)
            ui.meter(f"frmLand/{meter_slot}", 0.0, GAMETHEME.colors.info)
            ui.text(
                f"frmLand/{value_slot}",
                "—",
                tooltip="Land-cover percentages are not available in OpenPower data.",
                test_id=f"country.info.land_cover.{value_slot}",
            )

    def _render_human_development_frame(self, ui: GMLWidgets, model: CountryMoreInfoModel) -> None:
        ui.text("frmHumanDevelopment/lblTitle", "HUMAN DEVELOPMENT")
        country_value = self._format_percent(model.human_dev_pct)
        world_value = (
            self._format_percent(model.world_human_dev_pct)
            if model.world_human_dev_pct is not None
            else "—"
        )
        ui.text(
            "frmHumanDevelopment/frmInner/lblCountry",
            f"{model.name}: {country_value}",
            tooltip="OpenPower human-development index for this country.",
            test_id="country.info.hdi.country",
        )
        ui.meter(
            "frmHumanDevelopment/frmInner/picCountry",
            model.human_dev_pct / 100.0,
            GAMETHEME.colors.positive,
        )
        ui.text(
            "frmHumanDevelopment/frmInner/lblWorld",
            f"World: {world_value}",
            tooltip=(
                "REFERENCE derives world HDI from aggregated life expectancy, schooling and GDP per capita. "
                "OpenPower does not yet have all required inputs."
            ),
            test_id="country.info.hdi.world",
        )
        ui.meter(
            "frmHumanDevelopment/frmInner/picWorld",
            model.world_human_dev_pct / 100.0 if model.world_human_dev_pct is not None else 0.0,
            GAMETHEME.colors.warning,
        )
        draw_gml_separator(ui.path("frmHumanDevelopment/picSep"), color=GAMETHEME.colors.text_dim)
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

    def _render_population_frame(self, ui: GMLWidgets, model: CountryMoreInfoModel) -> None:
        ui.text("frmPopulation/lblTitle", "POPULATION")
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
        draw_gml_separator(ui.path("frmPopulation/picSep"), color=GAMETHEME.colors.text_dim)
        ui.text("frmPopulation/lblBirthRate", "Birth rate")
        ui.text(
            "frmPopulation/txtBirthRate",
            "—",
            tooltip="Birth-rate data is not available in OpenPower.",
            test_id="country.info.birth_rate.value",
        )
        ui.text("frmPopulation/lblDeathRate", "Death rate")
        ui.text(
            "frmPopulation/txtDeathRate",
            "—",
            tooltip="Death-rate data is not available in OpenPower.",
            test_id="country.info.death_rate.value",
        )

    def _render_terrain_frame(self, ui: GMLWidgets, model: CountryMoreInfoModel) -> None:
        ui.text("frmTerrain/lblTitle", "TERRAIN")
        ui.text("frmTerrain/lblLandArea", "Land area (km²)")
        ui.text(
            "frmTerrain/txtLandArea",
            self._format_int(model.land_area_km2) if model.land_area_available else "—",
            tooltip="Sum of OpenPower region areas under this country's control.",
            test_id="country.info.land_area.value",
        )
        ui.text("frmTerrain/lblWaterArea", "Water area")
        ui.text(
            "frmTerrain/txtWaterArea",
            "—",
            tooltip="Water-area data is not available in OpenPower.",
            test_id="country.info.water_area.value",
        )
        ui.text("frmTerrain/lblTotalArea", "Total area")
        ui.text(
            "frmTerrain/txtTotalArea",
            "—",
            tooltip="Total-area data is not available in OpenPower.",
            test_id="country.info.total_area.value",
        )

    def _render_climate_frame(self, ui: GMLWidgets) -> None:
        ui.text("frmClimate/lblTitle", "CLIMATE")
        ui.text(
            "frmClimate/frmInner/lblClimate",
            "—",
            tooltip="Climate identifiers are not available in OpenPower data.",
            test_id="country.info.climate.value",
        )

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

    def _draw_region_map(self, model: CountryMoreInfoModel, frame_w: float, frame_h: float) -> None:
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
        self._map_textures.draw_texture(texture, draw_w, draw_h, test_id="country.info.region_map")
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

    def _fit_texture(self, texture: CountryMapTexture, max_w: float, max_h: float) -> tuple[float, float]:
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
