from __future__ import annotations

import json

from modules.base.systems.military.capability_catalog import (
    DEFAULT_ROLE_PROFILES,
    canonical_role,
)
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.gml_layout import (
    active_gml_layout,
    draw_gml_separator,
    gml_child_frame,
    use_gml_layout,
)
from src.client.ui.panels.military.design_selection import UnitDesignSelection
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.military.unit_design_editor import UnitDesignEditor
from src.client.ui.panels.military.unit_design_widgets import (
    DESIGN_METRICS,
    capabilities_for_design,
    render_capability_rows,
)
from src.client.ui.panels.military.unit_type_options import unit_type_options_for_roles
from src.client.ui.panels.shared.panel_widgets import draw_required_tables


class UnitDesignPanel:
    """Show the selected design in the source-sized GDesignWindow frame."""

    def __init__(self, selection: UnitDesignSelection | None = None):
        self._presenter = MilitaryPresenter()
        self._editor = UnitDesignEditor()
        self._selection = selection or UnitDesignSelection()
        self._role = "infantry"
        self._details_tab = "unit_view"
        self._statistics_first_row = 0

    def render(self, state, context: PanelRenderContext) -> bool:
        editor_available = False
        with WindowManager.window(
            "UNIT DESIGN", x=300, y=150, w=324, h=414,
            test_id="unit_design.panel",
            gml_template="Unit_Design_New",
        ) as is_open:
            if not is_open:
                return False

            ui = GMLWidgets("Unit_Design_New")
            self._draw_source_frames(ui)
            editor_available = self._render_content(state, context, ui)

        if editor_available:
            self._editor.render(state, context)
        return True

    @staticmethod
    def _draw_source_frames(ui: GMLWidgets) -> None:
        for slot in (
            "frmInner/frmUnitInfo",
            "frmInner/tabGroups",
            "frmInner/frmUnitInfo1",
        ):
            ui.frame(slot)
        draw_gml_separator(
            ui.path("frmInner/frmUnitInfo/picSep"),
            color=GAMETHEME.colors.text_dim,
        )

    def _render_content(
        self, state, context: PanelRenderContext, ui: GMLWidgets | None = None,
    ) -> bool:
        ui = ui or GMLWidgets("Unit_Design_New")
        if not draw_required_tables(state, ("unit_designs",)):
            return False
        designs = self._presenter.designs_for_country(state, context.target_tag)
        all_designs_table = getattr(state, "tables", {}).get("unit_designs")
        all_designs = [] if all_designs_table is None else all_designs_table.to_dicts()
        selected_by_id = next(
            (row for row in designs if str(row.get("id") or "") == self._selection.design_id),
            None,
        )
        if selected_by_id is None and self._selection.design_id:
            selected_by_id = next(
                (row for row in all_designs if str(row.get("id") or "") == self._selection.design_id),
                None,
            )
            if selected_by_id is not None:
                designs.append(selected_by_id)
        if selected_by_id is not None:
            self._role = canonical_role(selected_by_id.get("class_name"))
        elif designs:
            self._role = canonical_role(designs[0].get("class_name"))
        role_options = unit_type_options_for_roles(DEFAULT_ROLE_PROFILES)
        role_names = [option.role for option in role_options]
        if self._role not in role_names:
            self._role = role_names[0]

        imgui.text_disabled(
            "UNIT TYPE",
            gml_id=ui.path("frmInner/frmUnitInfo/lblUnitType"),
        )
        _, role_index = imgui.combo(
            "##unit_design.preview.role", role_names.index(self._role),
            [option.label for option in role_options],
            test_id="unit_design.preview.role",
            gml_id=ui.path("frmInner/frmUnitInfo/cboUnitType"),
        )
        self._role = role_names[role_index]

        compatible_designs = [
            row for row in designs
            if canonical_role(row.get("class_name")) == self._role
        ]
        selected_design = next(
            (row for row in compatible_designs
             if str(row.get("id") or "") == self._selection.design_id),
            None,
        )
        design_labels = [str(row.get("display_name") or "Design") for row in compatible_designs]
        if not design_labels:
            design_labels = ["No saved designs"]
        selected_index = next(
            (index for index, row in enumerate(compatible_designs)
             if selected_design is not None and str(row.get("id") or "") == str(selected_design.get("id") or "")),
            0,
        )

        imgui.text_disabled(
            "DESIGN",
            gml_id=ui.path("frmInner/frmUnitInfo/lblUnitName"),
            test_id="unit_design.catalog.heading",
        )
        imgui.begin_disabled(not compatible_designs)
        changed, selected_index = imgui.combo(
            "##unit_design.preview.name", selected_index, design_labels,
            test_id="unit_design.preview.name",
            gml_id=ui.path("frmInner/frmUnitInfo/cboUnitName"),
        )
        imgui.end_disabled()
        if changed and compatible_designs:
            self._selection.select(compatible_designs[selected_index].get("id"))
            selected_design = compatible_designs[selected_index]

        if selected_design is None and compatible_designs:
            selected_design = compatible_designs[selected_index]

        description = self._design_description(selected_design)
        imgui.text_wrapped(
            description,
            gml_id=ui.path("frmInner/frmUnitInfo/frmDescription/txtText"),
        )
        self._source_text(ui, "frmInner/frmUnitInfo1/lblUnitCost", "UNIT COST")
        self._source_text(
            ui,
            "frmInner/frmUnitInfo1/txtCost",
            f"$ {float(selected_design.get('cost') or 0.0):,.0f}"
            if selected_design else "—",
        )

        self._render_tab_buttons(ui)
        if self._details_tab == "statistics":
            self._render_statistics(
                ui,
                capabilities_for_design(selected_design or {"class_name": self._role}),
            )
        else:
            self._render_overview(selected_design, ui)

        can_create = bool(context.is_own_country and context.net_client is not None)
        if active_gml_layout() is None:
            imgui.begin_disabled(not can_create)
            clicked = imgui.button("NEW DESIGN", test_id="unit_design.create.open")
            imgui.end_disabled()
        else:
            clicked = ui.button(
                "frmInner/btnNewDesign", "NEW DESIGN", "unit_design.create.open",
                enabled=can_create,
                tooltip="Create a design for the selected role." if can_create
                else "Select your own country and connect to create a design.",
            )
        if clicked:
            self._editor.open(self._role)
        return True

    @staticmethod
    def _source_text(ui: GMLWidgets, slot: str, value: object) -> None:
        if active_gml_layout() is None:
            imgui.text_disabled(str(value))
            return
        ui.text(slot, value)

    @staticmethod
    def _design_description(design: dict | None) -> str:
        if not design:
            return "No saved design for this role. Select NEW DESIGN to create one."
        name = str(design.get("display_name") or "Design")
        branch = str(design.get("branch") or "land").title()
        role = str(design.get("class_name") or "generic").replace("_", " ").title()
        return f"{name} · {branch} domain · fixed {role} role."

    def _render_tab_buttons(self, ui: GMLWidgets) -> None:
        # GTabbed places its fixed-width selectors in the bottom strip of this GML frame.
        tab_slot = "frmInner/tabGroups"
        tab_top = 179.0
        for index, (tab, label, test_id) in enumerate((
            ("unit_view", "UNIT VIEW", "unit_design.tab.unit_view"),
            ("statistics", "STATISTICS", "unit_design.tab.statistics"),
        )):
            selected = self._details_tab == tab
            imgui.push_style_color(
                imgui.Col_.button,
                GAMETHEME.colors.interaction_active if selected else GAMETHEME.colors.bg_input,
            )
            try:
                clicked = ui.button_at(
                    tab_slot,
                    label,
                    test_id,
                    offset=(index * 100.0, tab_top),
                    size=(101.0, 16.0),
                    padding=(1.0, 0.0),
                )
            finally:
                imgui.pop_style_color()
            if clicked:
                self._details_tab = tab

    def _render_statistics(
        self,
        ui: GMLWidgets,
        values: dict[str, float],
    ) -> None:
        session = active_gml_layout()
        list_slot = "frmInner/tabGroups/Tab2/frmList"
        specs_slot = f"{list_slot}/frmSpecs"
        if session is None:
            render_capability_rows(
                ui,
                specs_slot,
                values,
                test_id_prefix="unit_design.statistics",
            )
            return

        visible_count = 9
        max_first_row = max(0, len(DESIGN_METRICS) - visible_count)
        self._update_statistics_scroll(ui, max_first_row)
        visible_metrics = DESIGN_METRICS[
            self._statistics_first_row:self._statistics_first_row + visible_count
        ]
        list_rect = ui.rect(list_slot)
        if list_rect is None:
            return
        first_label = session.rect_for(
            ui.path(f"{specs_slot}/lbl{visible_metrics[0][2]}")
        )
        scroll_offset = first_label.y - list_rect.y - 3.0

        visible_keys = {key for key, _, _ in visible_metrics}
        with gml_child_frame(
            ui.path(list_slot),
            padding=(0.0, 0.0),
            bordered=False,
            window_flags=(
                imgui.WindowFlags_.no_scrollbar
                | imgui.WindowFlags_.no_scroll_with_mouse
            ),
            test_id="unit_design.statistics.list",
        ) as opened:
            if opened:
                parent_position = session.window_position
                # Child frames suspend parent GML placement; translate the same
                # session while the parent screen origin keeps GML slots exact.
                session.window_position = (
                    parent_position[0],
                    parent_position[1] - scroll_offset,
                )
                try:
                    with use_gml_layout(session):
                        render_capability_rows(
                            ui,
                            specs_slot,
                            values,
                            test_id_prefix="unit_design.statistics",
                            visible_keys=visible_keys,
                        )
                finally:
                    session.window_position = parent_position
        self._render_statistics_scrollbar(ui, max_first_row)

    def _update_statistics_scroll(self, ui: GMLWidgets, max_first_row: int) -> None:
        if max_first_row <= 0:
            self._statistics_first_row = 0
            return
        session = active_gml_layout()
        rect = ui.rect("frmInner/tabGroups/Tab2/frmList")
        if session is None or rect is None:
            return
        mouse = imgui.get_io().mouse_pos
        left = session.window_position[0] + rect.x
        top = session.window_position[1] + rect.y
        if left <= mouse.x <= left + rect.width and top <= mouse.y <= top + rect.height:
            wheel = float(imgui.get_io().mouse_wheel)
            if wheel:
                step = max(1, round(abs(wheel)))
                direction = -step if wheel > 0 else step
                self._statistics_first_row = max(
                    0,
                    min(max_first_row, self._statistics_first_row + direction),
                )

    def _render_statistics_scrollbar(self, ui: GMLWidgets, max_first_row: int) -> None:
        slot = "frmInner/tabGroups/Tab2/scrList"
        rect = ui.rect(slot)
        session = active_gml_layout()
        if rect is None or session is None:
            return

        clicked = ui.hitbox(
            slot,
            "unit_design.statistics.scrollbar",
            enabled=max_first_row > 0,
            tooltip="Scroll design statistics",
        )
        total_rows = len(DESIGN_METRICS)
        visible_rows = total_rows - max_first_row
        thumb_height = max(18.0, rect.height * visible_rows / total_rows)
        travel = max(0.0, rect.height - thumb_height)
        if max_first_row > 0 and (clicked or imgui.is_item_active()):
            local_y = float(imgui.get_io().mouse_pos.y) - session.window_position[1] - rect.y
            ratio = max(
                0.0,
                min(1.0, (local_y - thumb_height / 2.0) / max(1.0, travel)),
            )
            self._statistics_first_row = round(ratio * max_first_row)

        x = session.window_position[0] + rect.x
        y = session.window_position[1] + rect.y
        draw = imgui.get_window_draw_list()
        draw.add_rect_filled(
            (x, y), (x + rect.width, y + rect.height),
            imgui.get_color_u32(GAMETHEME.colors.bg_input),
        )
        thumb_y = y + travel * (
            self._statistics_first_row / max_first_row if max_first_row else 0.0
        )
        draw.add_rect_filled(
            (x + 2.0, thumb_y),
            (x + rect.width - 2.0, thumb_y + thumb_height),
            imgui.get_color_u32(GAMETHEME.colors.text_dim),
        )

    def _render_overview(self, design: dict | None, ui: GMLWidgets) -> None:
        session = active_gml_layout()
        rect = ui.rect("frmInner/tabGroups/Tab1/Container1")
        if session is None or rect is None:
            self._render_overview_flow(design)
            return

        origin_x = session.window_position[0] + rect.x + 8.0 - imgui.get_scroll_x()
        origin_y = session.window_position[1] + rect.y + 24.0 - imgui.get_scroll_y()
        imgui.set_cursor_screen_pos((origin_x, origin_y))
        imgui.text_disabled(
            "3D model preview unavailable in OpenPower.",
            test_id="unit_design.model.unavailable",
        )
        origin_y += 18.0
        if design is None:
            imgui.text_disabled("No design selected for this role.")
            imgui.set_cursor_screen_pos((origin_x, origin_y + 20.0))
            imgui.text_wrapped("Create a design to see its role profile and fixed target rules.")
            return

        if self._selection.design_id:
            imgui.text_disabled(
                f"Viewing design: {str(design.get('display_name') or 'Design')}",
                test_id="unit_design.detail.selected",
            )
            if ui.button_at(
                "frmInner/tabGroups/Tab1/Container1",
                "BACK",
                "unit_design.back_to_list",
                offset=(230.0, 4.0),
                size=(42.0, 14.0),
            ):
                self._selection.clear()
                return
        else:
            imgui.text_disabled("Fixed role definition")

        role = str(design.get("class_name") or "generic").lower()
        profile = DEFAULT_ROLE_PROFILES.get(role)
        domain = str(design.get("domain") or (profile.domain if profile else "unknown")).title()
        quality = float(design.get("quality") or 0.0) * 100.0
        speed = float(design.get("speed") or 0.0) * 100.0
        firepower = float(design.get("firepower") or 0.0) * 100.0
        imgui.set_cursor_screen_pos((origin_x, origin_y + 19.0))
        imgui.text_disabled(f"{domain} · {role.replace('_', ' ').title()}")
        imgui.set_cursor_screen_pos((origin_x, origin_y + 37.0))
        imgui.text_disabled(
            f"Quality {quality:.0f}%  Speed {speed:.0f}%  Firepower {firepower:.0f}%"
        )

        targets = self._decode_list(design.get("valid_targets_json"))
        vulnerabilities = self._decode_list(design.get("vulnerabilities_json"))
        current_y = origin_y + 55.0
        for line in (
            "Design-adjustable capabilities are bounded by the role catalog.",
            "Fixed targets: " + (", ".join(targets) or "neutral"),
            "Fixed counter vulnerabilities: " + (", ".join(vulnerabilities) or "none configured"),
        ):
            imgui.set_cursor_screen_pos((origin_x, current_y))
            imgui.push_text_wrap_pos(imgui.get_cursor_pos_x() + max(1.0, rect.width - 16.0))
            imgui.text_wrapped(line)
            imgui.pop_text_wrap_pos()
            current_y = imgui.get_cursor_screen_pos().y + 2.0

    @staticmethod
    def _render_overview_flow(design: dict | None) -> None:
        if design is None:
            imgui.text_disabled("No design selected for this role.")
            return
        imgui.text_disabled("Fixed role definition")
        imgui.text_disabled("Design-adjustable capabilities are bounded by the role catalog")
        imgui.text_wrapped(
            "Fixed targets: "
            + (", ".join(UnitDesignPanel._decode_list(design.get("valid_targets_json"))) or "neutral")
        )
        imgui.text_wrapped(
            "Fixed counter vulnerabilities: "
            + (", ".join(UnitDesignPanel._decode_list(design.get("vulnerabilities_json"))) or "none configured")
        )

    @staticmethod
    def _decode_list(value) -> list[str]:
        try:
            parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError):
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
