from __future__ import annotations

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.gml_layout import active_gml_layout, gml_child_frame
from src.client.ui.layouts.gml_rows import gml_row
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.military.unit_training_confirmation import (
    training_offer,
    training_unavailable_reason,
)
from src.shared.actions import ActionDispatchUnitDeployment


_GML_ROOT = "Unit_Ground_Deployment_Window"
_CATEGORY_NAMES = ("GROUND", "AIR", "NAVAL", "STRATEGIC")
_CATEGORY_LISTS = (
    "frmInner/tabGroups/Tab4/lstDeploy",
    "frmInner/tabGroups/Tab1/lstDeploy",
    "frmInner/tabGroups/Tab3/lstDeploy",
    "frmInner/tabGroups/Tab2/lstDeploy",
)
_ROW_WIDTH = 437.0
_ROW_HEIGHT = 18.0


class UnitReservesPanel:
    """Present ready-to-deploy groups in REFERENCE's four-category deployment window."""

    def __init__(self, open_train_cb=None) -> None:
        self._presenter = MilitaryPresenter()
        self._open_train_cb = open_train_cb
        self._active_category = 0
        self._selected_unit_ids: set[str] = set()
        self._selection_anchor_unit_id: str | None = None

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window(
            "UNDEPLOYED TROOPS",
            x=400,
            y=150,
            w=507,
            h=390,
            test_id="unit_reserves.panel",
            gml_template=_GML_ROOT,
        ) as is_open:
            if not is_open:
                return False

            ui = GMLWidgets(_GML_ROOT)
            session = active_gml_layout()
            if session is not None:
                session.apply_tab_page_runtime_geometry(ui.path("frmInner/tabGroups"))
            ui.frame("frmInner")
            ui.frame("frmInner/tabGroups")
            if not context.is_own_country:
                ui.text(
                    "frmInner/lblHelp",
                    "Deployment groups are visible only for your country.",
                    test_id="unit_reserves.restricted",
                )
                for category, slot in enumerate(self._quantity_slots()):
                    ui.text(slot, "—", test_id=f"unit_reserves.count.{_CATEGORY_NAMES[category].casefold()}")
                return True

            country_tag = str(context.target_tag or "").strip().upper()
            groups = self._presenter.reserve_units_for_country(state, country_tag)
            categorized = self._categorize(groups)
            visible_ids = {
                str(row.get("unit_id") or "")
                for row in categorized[self._active_category]
            }
            selected_count = len(self._selected_unit_ids & visible_ids)
            help_text = (
                "Select reserve groups to train or deploy to the capital or map."
                if selected_count == 0
                else f"{selected_count} group(s) selected; choose Train, Deploy or drag to map."
            )
            ui.text(
                "frmInner/lblHelp",
                help_text,
                max_width=455.0,
                test_id="unit_reserves.help",
            )
            self._render_category_counts(categorized, ui)
            self._render_group_list(categorized[self._active_category], ui, context)
            self._render_actions(state, country_tag, categorized[self._active_category], ui, context)
            self._render_category_tabs(categorized, ui)
            return True

    @staticmethod
    def _quantity_slots() -> tuple[str, ...]:
        return tuple(
            f"frmInner/{name}"
            for name in ("txtQty", "txtQty1", "txtQty2", "txtQty3")
        )

    @staticmethod
    def _categorize(groups: list[dict]) -> tuple[list[dict], ...]:
        buckets: tuple[list[dict], ...] = ([], [], [], [])
        for row in groups:
            unit_type = str(row.get("unit_type") or "").casefold()
            domain = str(row.get("unit_domain") or "").casefold()
            combined = f"{domain} {unit_type}"
            if any(token in combined for token in ("nuclear", "strategic", "missile")):
                index = 3
            elif any(token in combined for token in ("naval", "ship", "submarine", "fleet")):
                index = 2
            elif any(token in combined for token in ("air", "fighter", "aircraft", "bomber")):
                index = 1
            else:
                index = 0
            buckets[index].append(row)
        return buckets

    def _render_category_counts(
        self,
        groups_by_category: tuple[list[dict], ...],
        ui: GMLWidgets,
    ) -> None:
        for label, slot, groups in zip(_CATEGORY_NAMES, self._quantity_slots(), groups_by_category):
            count = len(groups)
            ui.frame(slot)
            ui.text(
                slot,
                count,
                tooltip=f"{label.title()} deployment groups: {count}",
                test_id=f"unit_reserves.count.{label.casefold()}",
            )

    def _render_category_tabs(
        self,
        groups_by_category: tuple[list[dict], ...],
        ui: GMLWidgets,
    ) -> None:
        tab_group = "frmInner/tabGroups"
        session = active_gml_layout()
        tab_layout = session.apply_tab_page_runtime_geometry(ui.path(tab_group)) if session else None
        if session is None or tab_layout is None:
            return

        group_rect = session.rect_for(ui.path(tab_group))
        for index, (label, groups) in enumerate(zip(_CATEGORY_NAMES, groups_by_category)):
            button_rect = session.tab_button_rect(ui.path(tab_group), index)
            if button_rect is None:
                continue
            offset = (button_rect.x - group_rect.x, button_rect.y - group_rect.y)
            selected = index == self._active_category
            imgui.push_style_color(
                imgui.Col_.button,
                GAMETHEME.colors.interaction_active if selected else GAMETHEME.colors.bg_input,
            )
            try:
                clicked = ui.button_at(
                    tab_group,
                    label,
                    f"unit_reserves.category.{label.casefold()}",
                    offset=offset,
                    size=(button_rect.width, button_rect.height),
                    enabled=True,
                    tooltip=f"Show {label.lower()} reserve groups ({len(groups)})",
                    padding=(1.0, 0.0),
                )
            finally:
                imgui.pop_style_color()
            if clicked and self._active_category != index:
                self._active_category = index
                self._selected_unit_ids.clear()
                self._selection_anchor_unit_id = None

    def _render_group_list(
        self,
        groups: list[dict],
        ui: GMLWidgets,
        context: PanelRenderContext,
    ) -> None:
        list_slot = _CATEGORY_LISTS[self._active_category]
        with gml_child_frame(ui.path(list_slot), padding=(0.0, 0.0), bordered=True) as opened:
            if not opened:
                return

            if not groups:
                imgui.text_disabled(
                    f"No {_CATEGORY_NAMES[self._active_category].lower()} groups are awaiting deployment.",
                    test_id="unit_reserves.empty",
                )
                return

            imgui.push_style_var(imgui.StyleVar_.item_spacing, (0.0, 0.0))
            try:
                for row in groups:
                    self._render_group_row(row, groups, context)
            finally:
                imgui.pop_style_var()

    def _render_group_row(
        self,
        row: dict,
        visible_groups: list[dict],
        context: PanelRenderContext,
    ) -> None:
        unit_id = str(row.get("unit_id") or "").strip()
        if not unit_id:
            return

        start = imgui.get_cursor_screen_pos()
        selected = unit_id in self._selected_unit_ids
        draw = imgui.get_window_draw_list()
        row_min = (float(start.x), float(start.y))
        row_max = (row_min[0] + _ROW_WIDTH, row_min[1] + _ROW_HEIGHT)
        if selected:
            draw.add_rect_filled(
                row_min,
                row_max,
                imgui.get_color_u32((0.25, 0.27, 0.3, 0.72)),
            )

        type_text = str(row.get("unit_type") or "Unit").replace("_", " ").title()
        quantity = max(0, int(row.get("quantity") or 0))
        design_name = str(row.get("design_name") or type_text)
        row_text = UIPrimitives.fit_text(f"{quantity:,} {design_name}".replace(",", " "), 242.0)

        lifecycle = str(row.get("lifecycle") or "").casefold()
        progress = max(0.0, min(1.0, float(row.get("training_progress") or 0.0)))
        if str(row.get("training_level") or "Recruit").casefold() != "recruit" and lifecycle != "training":
            progress = 1.0
        state_text = str(row.get("blocking_reason") or "")
        if not state_text:
            state_text = (
                f"Training {progress:.0%}"
                if lifecycle == "training" else
                str(row.get("status") or "Ready to deploy").replace("_", " ").title()
            )

        with gml_row("lstUnitDeployItem", unit_id) as row_ui:
            row_ui.text(
                "txtName",
                row_text,
                tooltip=row_text,
                test_id=f"unit_reserves.row.name.{unit_id}",
            )
            row_ui.meter("frmProgress", progress, GAMETHEME.colors.positive)
            row_ui.text_at(
                "frmProgress",
                state_text,
                offset=(6.0, 1.0),
                max_width=150.0,
                color=GAMETHEME.colors.text_dim,
                tooltip=state_text,
                test_id=f"unit_reserves.row.status.{unit_id}",
            )

        # Selection uses one source-sized hitbox; dynamic row children remain
        # anchored to their exported GML slots above.
        imgui.set_cursor_screen_pos(start)
        clicked = imgui.invisible_button(
            f"##deployment-group-{unit_id}",
            (_ROW_WIDTH, _ROW_HEIGHT),
            test_id=f"unit_reserves.row.{unit_id}",
        )
        if clicked:
            visible_ids = [str(group.get("unit_id") or "") for group in visible_groups]
            self._update_selection(unit_id, visible_ids)
            selected = unit_id in self._selected_unit_ids

        imgui.set_cursor_screen_pos((start.x, start.y + _ROW_HEIGHT))

        if imgui.is_item_hovered():
            tooltip = f"{row_text} · {state_text}"
            imgui.set_tooltip(tooltip)

        if (
            context.on_deployment_drag_start is not None
            and imgui.is_item_active()
            and imgui.is_mouse_dragging(imgui.MouseButton_.left)
            and lifecycle != "training"
        ):
            # The source list supports dragging a multi-selection as one map order.
            context.on_deployment_drag_start(sorted(self._selected_unit_ids))

    def _update_selection(self, unit_id: str, visible_ids: list[str]) -> None:
        io = imgui.get_io()
        anchor = self._selection_anchor_unit_id
        if io.key_shift and anchor in visible_ids:
            start, end = sorted((visible_ids.index(anchor), visible_ids.index(unit_id)))
            self._selected_unit_ids = set(visible_ids[start : end + 1])
        elif io.key_ctrl:
            if unit_id in self._selected_unit_ids:
                self._selected_unit_ids.remove(unit_id)
            else:
                self._selected_unit_ids.add(unit_id)
            self._selection_anchor_unit_id = unit_id
        else:
            self._selected_unit_ids = {unit_id}
            self._selection_anchor_unit_id = unit_id

    def _render_actions(
        self,
        state,
        country_tag: str,
        groups: list[dict],
        ui: GMLWidgets,
        context: PanelRenderContext,
    ) -> None:
        visible_ids = {str(row.get("unit_id") or "") for row in groups}
        selected_ids = sorted(self._selected_unit_ids & visible_ids)
        selected_rows = [row for row in groups if str(row.get("unit_id") or "") in selected_ids]
        dispatchable = [
            row for row in selected_rows
            if str(row.get("lifecycle") or "").casefold() != "training"
        ]
        capital_region = _capital_region_id(state, country_tag)
        is_strategic_tab = self._active_category == 3
        deploy_enabled = bool(dispatchable) and capital_region is not None and not is_strategic_tab
        if deploy_enabled:
            deploy_tooltip = "Dispatch selected groups to your capital."
        elif is_strategic_tab:
            deploy_tooltip = "REFERENCE disables capital deployment for strategic missile groups."
        elif capital_region is None:
            deploy_tooltip = "The current country snapshot does not identify a capital region."
        elif selected_rows and not dispatchable:
            deploy_tooltip = "Groups in training cannot be dispatched."
        else:
            deploy_tooltip = "Select one or more groups first."

        if ui.button(
            "frmInner/btnDeploy",
            "DEPLOY TO CAPITAL",
            "unit_reserves.deploy_capital",
            enabled=deploy_enabled and context.net_client is not None,
            dynamic_enabled=True,
            tooltip=deploy_tooltip,
        ):
            for row in dispatchable:
                context.net_client.send_action(ActionDispatchUnitDeployment(
                    context.net_client.player_id,
                    str(row["unit_id"]),
                    int(capital_region),
                    0,
                ))

        trainable_ids = [
            unit_id for unit_id in selected_ids
            if training_offer(state, unit_id, country_tag) is not None
        ]
        can_train = bool(trainable_ids) and context.net_client is not None and self._open_train_cb is not None
        if not selected_ids:
            train_tooltip = "Select one or more groups first."
        elif not can_train:
            train_tooltip = training_unavailable_reason(state, selected_ids[0], country_tag)
        else:
            train_tooltip = f"Review training terms for {len(trainable_ids)} selected group(s)."

        if ui.button(
            "frmInner/btnTrain",
            "TRAIN SELECTED",
            "unit_reserves.train",
            enabled=can_train,
            dynamic_enabled=True,
            tooltip=train_tooltip,
        ):
            if self._open_train_cb(state, trainable_ids):
                self._selected_unit_ids.difference_update(trainable_ids)


def _capital_region_id(state, country_tag: str) -> int | None:
    governments = state.tables.get("country_governments")
    if governments is None or governments.is_empty():
        return None
    row = next((
        item for item in governments.to_dicts()
        if str(item.get("country_id") or "").strip().upper() == country_tag
    ), None)
    try:
        capital = int((row or {}).get("capital_region_id") or 0)
    except (TypeError, ValueError):
        return None
    return capital if capital > 0 else None
