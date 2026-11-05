from collections.abc import Callable
from typing import Optional, Any
from src.client.ui.core.instrumented_imgui import imgui

from src.client.ui.core.composer import UIComposer
from src.client.ui.components.hud.panel_manager import PanelManager
from src.client.ui.core.testability import semantic_region
from src.shared.treaties import treaty_type_labels

class ContextMenu:
    """
    Manages the Global Right-Click Context Menu for the map.
    Handles the 'queued open' logic to prevent ImGui event conflicts.
    """
    def __init__(
        self,
        composer: UIComposer,
        panel_manager: PanelManager,
        viewport_ctrl: Any,
        has_selected_units: Callable[[], bool] | None = None,
        on_move_selected_units: Callable[[], None] | None = None,
        on_quick_treaty: Callable | None = None,
    ):
        self.composer = composer
        self.panels = panel_manager
        self.viewport = viewport_ctrl
        self._has_selected_units = has_selected_units
        self._on_move_selected_units = on_move_selected_units
        self._on_quick_treaty = on_quick_treaty
        self._state = None
        self._player_tag = ""

        # State
        self._target_id: Optional[int] = None
        self._queued_open: bool = False
        self._popup_id = "global_map_context"

    def show(self, region_id: int):
        """
        Public API to trigger the menu. Safe to call from Input handlers.
        """
        self._target_id = region_id
        self._queued_open = True

    def render(self, state=None, player_tag=""):
        """
        Must be called within the ImGui frame loop.
        """
        self._state, self._player_tag = state, player_tag
        # 1. Handle Queued Open (Safe point inside Frame)
        if self._queued_open:
            imgui.open_popup(self._popup_id)
            self._queued_open = False

        # 2. Render Popup Content
        if self.composer.begin_popup(self._popup_id):
            with semantic_region("map.context.menu", "Map context menu"):
                self._render_content()
            self.composer.end_popup()

    def _render_content(self):
        self._render_target_actions()
        self._render_map_modes()
        self._render_unit_visibility()
        self._render_tools()
        self._render_system_actions()

    def _render_target_actions(self):
        if self._target_id is not None:
            imgui.text_disabled(f"Target: Region #{self._target_id}")

            target_tag = self._target_country()
            foreign_target = bool(target_tag and target_tag != self._player_tag)
            if self._has_selected_units is not None and self._has_selected_units():
                move_label = "Occupy Territory" if foreign_target else "Move"
                move_test_id = "map.context.occupy" if foreign_target else "map.context.move"
                if (
                    self.composer.draw_menu_item(move_label, "M", test_id=move_test_id)
                    and self._on_move_selected_units is not None
                ):
                    self._on_move_selected_units()
                imgui.separator()

            if self.composer.draw_menu_item("View Details", "I"):
                self.panels.set_visible("INSPECTOR", True)
                self.viewport.select_region_by_id(self._target_id)

            if self.composer.draw_menu_item("More Info", "F"):
                self.panels.set_visible("COUNTRY_MORE_INFO", True)
                self.viewport.select_region_by_id(self._target_id)

            if self.composer.draw_menu_item("Center Camera"):
                self.viewport.focus_on_region(self._target_id)

            imgui.separator()

            if target_tag and target_tag != self._player_tag and self._on_quick_treaty is not None:
                if self.composer.begin_menu("Diplomacy"):
                    for treaty_type, label in treaty_type_labels():
                        if treaty_type == "mobility_agreement":
                            continue
                        if imgui.menu_item(label, "", False, True,
                                           test_id=f"map.treaty.{treaty_type}")[0]:
                            self._on_quick_treaty(target_tag, treaty_type, False)
                    for treaty_type, label in (("assume_foreign_debt", "Request debt assumption"),
                                               ("free_region", "Request region liberation")):
                        if imgui.menu_item(label, "", False, True,
                                           test_id=f"map.treaty.{treaty_type}.inverted")[0]:
                            self._on_quick_treaty(target_tag, treaty_type, True)
                    self.composer.end_menu()

    def _render_map_modes(self):
        if self.composer.begin_menu("Map Mode"):
            # A. Terrain (Physical) Toggle
            if self.composer.draw_menu_item("Physical (Terrain)"):
                # Switches to terrain mode.
                # Requires ViewportController.set_map_mode("terrain") to handle disabling overlays.
                if hasattr(self.viewport, "set_map_mode"):
                    self.viewport.set_map_mode("terrain")

            imgui.separator()

            # B. Dynamic Modes (Political, Economic, etc.)
            if hasattr(self.viewport, "map_modes"):
                for key, mode_obj in self.viewport.map_modes.items():
                    # Highlight if active
                    is_active = (getattr(self.viewport, "current_mode_key", "") == key)

                    if imgui.menu_item(
                        mode_obj.name, "", is_active,
                        test_id=f"map.context.mode.{key}",
                    )[0]:
                        self.viewport.set_map_mode(key)

            self.composer.end_menu()

    def _render_unit_visibility(self):
        if hasattr(self.viewport, "show_all_units"):
            imgui.separator()
            if self.composer.begin_menu("Units Visibility"):
                if imgui.menu_item("Show All Units Globally", "", self.viewport.show_all_units)[0]:
                    self.viewport.show_all_units = not self.viewport.show_all_units
                if hasattr(self.viewport, "show_engagement_zones"):
                    if imgui.menu_item("Show Engagement Zones", "", self.viewport.show_engagement_zones)[0]:
                        self.viewport.show_engagement_zones = not self.viewport.show_engagement_zones
                self.composer.end_menu()

    def _render_tools(self):
        # Check if the Data Inspector panel is registered before showing the menu
        has_data_inspector = any(e.id == "DATA_INSPECTOR" for e in self.panels.get_entries())

        if has_data_inspector:
            imgui.separator()
            if self.composer.begin_menu("Tools"):
                is_visible = self.panels.is_visible("DATA_INSPECTOR")
                if imgui.menu_item("Data Inspector", "", is_visible)[0]:
                    self.panels.toggle("DATA_INSPECTOR")
                self.composer.end_menu()

    def _render_system_actions(self):
        imgui.separator()
        if self.composer.draw_menu_item("Close All Panels"):
            for entry in self.panels.get_entries():
                # Directly hiding a panel skips its unsaved-changes confirmation.
                self.panels.set_visible(entry.id, False)

    def _target_country(self):
        if self._state is None or self._target_id is None:
            return ""
        regions = self._state.tables.get("regions")
        if regions is None:
            return ""
        import polars as pl
        selected = regions.filter(pl.col("id") == self._target_id)
        if selected.is_empty():
            return ""
        region = selected.row(0, named=True)
        tag = str(region.get("controller") or region.get("owner") or "").upper()
        countries = self._state.tables.get("countries")
        # Unowned regions must not silently prepare a treaty with the editor's
        # first available country when their controller is absent or invalid.
        if countries is None or "id" not in countries.columns:
            return ""
        return tag if countries.filter(pl.col("id") == tag).height else ""
