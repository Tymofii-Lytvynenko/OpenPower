from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import polars as pl
from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.theme import GAMETHEME

if TYPE_CHECKING:
    from src.shared.state import GameState


@dataclass(frozen=True, slots=True)
class UnitRosterEntry:
    """A normalized row for the unit details roster table."""

    troop_type: str
    quantity: int
    name: str
    location: str
    status: str


@dataclass(frozen=True, slots=True)
class UnitDetailsViewModel:
    """Presentation-ready unit details resolved from the authoritative game state."""

    unit_id: str
    owner_name: str
    unit_label: str
    entries: tuple[UnitRosterEntry, ...]


class UnitDetailsPresenter:
    """Builds a lightweight view model for the unit details window."""

    def build(self, state: Optional["GameState"], unit_id: Optional[str]) -> Optional[UnitDetailsViewModel]:
        if state is None or not unit_id or "units" not in state.tables:
            return None

        units = state.tables["units"]
        if units.is_empty() or "id" not in units.columns:
            return None

        unit_rows = units.filter(pl.col("id") == unit_id)
        if unit_rows.is_empty():
            return None

        unit = unit_rows.to_dicts()[0]
        owner_tag = str(unit.get("owner", "") or "")
        owner_name = self._resolve_country_name(state, owner_tag)
        location_name = self._resolve_region_name(state, int(unit.get("current_region_id", 0) or 0))
        status = "Moving" if bool(unit.get("is_moving", False)) else "Parked"
        quantity = max(1, int(unit.get("strength", 1) or 1))

        entry = UnitRosterEntry(
            troop_type="Infantry",
            quantity=quantity,
            name=f"{owner_name} personnel",
            location=location_name,
            status=status,
        )
        return UnitDetailsViewModel(
            unit_id=unit_id,
            owner_name=owner_name,
            unit_label=f"{owner_name} field unit",
            entries=(entry,),
        )

    def _resolve_country_name(self, state: "GameState", owner_tag: str) -> str:
        countries = state.tables.get("countries")
        if countries is None or countries.is_empty() or "id" not in countries.columns:
            return owner_tag or "Unknown"

        if "name" in countries.columns:
            match = countries.filter(pl.col("id") == owner_tag).select("name")
            if not match.is_empty():
                name = match.item(0, 0)
                if name:
                    return str(name)

        return owner_tag or "Unknown"

    def _resolve_region_name(self, state: "GameState", region_id: int) -> str:
        if region_id <= 0:
            return "Unknown"

        regions = state.tables.get("regions")
        if regions is None or regions.is_empty() or "id" not in regions.columns:
            return f"Region {region_id}"

        if "name" in regions.columns:
            match = regions.filter(pl.col("id") == region_id).select("name")
            if not match.is_empty():
                name = match.item(0, 0)
                if name:
                    return str(name)

        return f"Region {region_id}"


class UnitDetailsWindow:
    """Floating details window opened from the world map on unit double-click."""

    def __init__(self, presenter: Optional[UnitDetailsPresenter] = None):
        self._presenter = presenter or UnitDetailsPresenter()
        self._is_open = False
        self._unit_id: Optional[str] = None

    def open_for_unit(self, unit_id: str) -> None:
        self._unit_id = unit_id
        self._is_open = True

    def render(self, state: Optional["GameState"]) -> None:
        if not self._is_open or not self._unit_id:
            return

        model = self._presenter.build(state, self._unit_id)
        if model is None:
            self._is_open = False
            self._unit_id = None
            return

        with WindowManager.window(
            f"UNIT LIST##{model.unit_id}",
            x=120,
            y=110,
            w=760,
            h=420,
        ) as is_open:
            if not is_open:
                self._is_open = False
                self._unit_id = None
                return

            self._render_header(model)
            self._render_roster_table(model)
            imgui.dummy((0.0, 12.0))
            imgui.text_disabled("Only infantry is available for now.")

    def _render_header(self, model: UnitDetailsViewModel) -> None:
        imgui.text_disabled("UNIT TYPE")
        imgui.same_line()
        imgui.set_next_item_width(150)
        if imgui.begin_combo("##unit_type_filter", "All"):
            imgui.selectable("All", True)
            imgui.end_combo()

        imgui.same_line()
        imgui.text_colored(GAMETHEME.colors.text_dim, f"{model.owner_name} | {model.unit_label}")
        imgui.separator()

    def _render_roster_table(self, model: UnitDetailsViewModel) -> None:
        table_flags = (
            imgui.TableFlags_.borders
            | imgui.TableFlags_.row_bg
            | imgui.TableFlags_.scroll_y
            | imgui.TableFlags_.sizing_stretch_prop
        )

        if not imgui.begin_table("##unit_roster", 5, table_flags, (0.0, -28.0)):
            return

        imgui.table_setup_column("TYPE", imgui.TableColumnFlags_.width_fixed, 120.0)
        imgui.table_setup_column("QTY", imgui.TableColumnFlags_.width_fixed, 70.0)
        imgui.table_setup_column("NAME", imgui.TableColumnFlags_.width_stretch, 180.0)
        imgui.table_setup_column("LOCATION", imgui.TableColumnFlags_.width_stretch, 170.0)
        imgui.table_setup_column("STATUS", imgui.TableColumnFlags_.width_fixed, 100.0)
        imgui.table_headers_row()

        for entry in model.entries:
            imgui.table_next_row()

            imgui.table_next_column()
            imgui.text(entry.troop_type)

            imgui.table_next_column()
            imgui.text(f"{entry.quantity:,}".replace(",", " "))

            imgui.table_next_column()
            imgui.text(entry.name)

            imgui.table_next_column()
            imgui.text(entry.location)

            imgui.table_next_column()
            status_color = GAMETHEME.colors.info if entry.status == "Moving" else GAMETHEME.colors.text_main
            imgui.text_colored(status_color, entry.status)

        imgui.end_table()
