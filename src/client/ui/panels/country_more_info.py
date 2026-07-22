from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import polars as pl
from imgui_bundle import imgui

from src.client.renderers.country_region_map import CountryMapTexture, CountryRegionMapTextureCache
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME
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
    density_per_km2: float
    human_dev_pct: float
    world_human_dev_pct: float
    infrastructure_pct: float
    telecom_pct: float
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

        return CountryMoreInfoModel(
            tag=tag,
            name=resolve_country_name(state, tag),
            region_ids=region_ids,
            region_count=len(region_ids),
            land_area_km2=land_area,
            world_area_share_pct=(land_area / world_area * 100.0) if world_area > 0 else 0.0,
            population_total=population_total,
            population_bands=population_bands,
            density_per_km2=(population_total / land_area) if land_area > 0 else 0.0,
            human_dev_pct=as_percent(country_row.get("human_dev")),
            world_human_dev_pct=self._world_average_pct(state, "human_dev"),
            infrastructure_pct=as_percent(country_row.get("budget_infra_ratio")),
            telecom_pct=as_percent(country_row.get("budget_telecom_ratio")),
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

    def _world_average_pct(self, state, column: str) -> float:
        countries = getattr(state, "tables", {}).get("countries")
        if countries is None or countries.is_empty() or column not in countries.columns:
            return 0.0
        try:
            return as_percent(countries[column].mean())
        except Exception:
            return 0.0

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
        with WindowManager.window(title, x=420, y=100, w=780, h=620) as is_open:
            if not is_open:
                return False

            imgui.begin_child("CountryMoreInfoScroll", (0, 0), False)
            try:
                self._render_content(model)
            finally:
                imgui.end_child()

            return True

    def _render_content(self, model: CountryMoreInfoModel) -> None:
        table_flags = imgui.TableFlags_.sizing_stretch_prop | imgui.TableFlags_.borders_inner_v
        if not imgui.begin_table("country_more_info_columns", 2, table_flags):
            self._render_map_column(model)
            imgui.separator()
            self._render_stats_column(model)
            return

        try:
            imgui.table_setup_column("Map", imgui.TableColumnFlags_.width_fixed, 365.0)
            imgui.table_setup_column("Stats", imgui.TableColumnFlags_.width_stretch)
            imgui.table_next_row()

            imgui.table_next_column()
            self._render_map_column(model)

            imgui.table_next_column()
            self._render_stats_column(model)
        finally:
            imgui.end_table()

    def _render_map_column(self, model: CountryMoreInfoModel) -> None:
        Prims.header("REGION MAP")
        self._render_map_frame(model)

        imgui.dummy((0, 8))
        Prims.header("REGIONAL MAKEUP", show_bg=False)
        if model.composition_rows:
            for row in model.composition_rows:
                Prims.meter_row(row.label, row.percent, row.color, row.value, label_width=125.0)
        else:
            imgui.text_disabled("No regional composition data.")

        imgui.dummy((0, 8))
        Prims.header("TERRAIN", show_bg=False)
        Prims.value_row("Land area (km2)", self._format_int(model.land_area_km2))
        Prims.value_row("World share", f"{model.world_area_share_pct:.2f} %")
        Prims.value_row("Regions", self._format_int(model.region_count))
        Prims.value_row("Density", f"{model.density_per_km2:.1f} / km2")

    def _render_stats_column(self, model: CountryMoreInfoModel) -> None:
        Prims.header("HUMAN DEVELOPMENT LEVEL")
        Prims.meter_row(model.name, model.human_dev_pct, GAMETHEME.colors.positive)
        Prims.meter_row("World average", model.world_human_dev_pct, GAMETHEME.colors.warning)

        imgui.dummy((0, 8))
        Prims.header("INFRASTRUCTURE", show_bg=False)
        Prims.meter_row("Infrastructure", model.infrastructure_pct, GAMETHEME.colors.info)
        Prims.meter_row("Telecom", model.telecom_pct, GAMETHEME.colors.demographics)
        Prims.meter_row("Poverty", model.poverty_pct, GAMETHEME.colors.negative)

        imgui.dummy((0, 8))
        Prims.header("POPULATION")
        for band in model.population_bands:
            value = f"{self._format_int(band.value)}    {band.percent:.1f} %"
            Prims.value_row(band.label, value, label_width=130.0)
        Prims.value_row("Total", self._format_int(model.population_total), GAMETHEME.colors.accent, 130.0)

        imgui.dummy((0, 6))
        Prims.value_row("Fertility rate", f"{model.fertility_rate:.2f}", label_width=130.0)
        Prims.value_row("Life expectancy", f"{model.life_expectancy:.1f}", label_width=130.0)

        imgui.dummy((0, 8))
        Prims.header("PRODUCTION MIX", show_bg=False)
        if model.production_rows:
            for row in model.production_rows:
                Prims.meter_row(row.label, row.percent, row.color, row.value, label_width=150.0)
        else:
            imgui.text_disabled("No production data.")

        imgui.dummy((0, 8))
        Prims.header("CLIMATE / REGIONS", show_bg=False)
        imgui.text_wrapped(model.region_summary)

    def _render_map_frame(self, model: CountryMoreInfoModel) -> None:
        frame_w = imgui.get_content_region_avail().x
        frame_h = 245.0
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
            0,
            1.5,
        )

        map_data = self._map_data_provider()
        texture = self._map_textures.get_texture(map_data, model.region_ids)
        if texture is None:
            self._render_map_placeholder(p, frame_w, frame_h)
            imgui.set_cursor_screen_pos((p.x, p.y + frame_h + 6.0))
            return

        draw_w, draw_h = self._fit_texture(texture, frame_w - 14.0, frame_h - 14.0)
        draw_x = p.x + (frame_w - draw_w) * 0.5
        draw_y = p.y + (frame_h - draw_h) * 0.5
        imgui.set_cursor_screen_pos((draw_x, draw_y))
        self._map_textures.draw_texture(texture, draw_w, draw_h)
        imgui.set_cursor_screen_pos((p.x, p.y + frame_h + 6.0))

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