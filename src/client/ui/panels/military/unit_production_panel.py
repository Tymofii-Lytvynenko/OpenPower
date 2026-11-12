from __future__ import annotations

from src.client.services.client_presentation import contribution_for
from src.client.ui.components.shared.gml_value_repeat import GMLValueRepeatPair
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.formatting import format_currency
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.gml_layout import active_gml_layout, gml_child_frame
from src.client.ui.layouts.gml_rows import gml_row
from src.client.ui.panels.military import production_snapshot
from src.client.ui.panels.military.design_selection import supports_design_details
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.shared.actions import (
    ActionCancelForeignUnitOrder,
    ActionCancelProductionOrder,
    ActionDispatchUnitDeployment,
    ActionQueueUnitProduction,
    ActionRequestForeignUnitOrder,
    ActionRespondForeignUnitOrder,
    ActionSetForeignOrderAcceptance,
    ActionSetProductionPaused,
    ActionSetProductionPriority,
)
from src.shared.military_constants import (
    MAX_PRODUCTION_QUEUE_ORDERS,
    MAX_UNIT_PRODUCTION_QUANTITY,
)
from src.shared.mod_api import ClientPresentationKeys

_ROOT = "Unit_Production_Window"
_GML_TEMPLATE = "Unit_Production_Window"
_DESIGN_TREE_SLOT = "frmDesignList/frmDesignList/frmList/frmInner"
_PRODUCTION_LIST_SLOT = "frmRight/frmProduction/lstProduction"
_CATEGORIES = (
    ("ground", "GROUND", "frmDesignList/frmFilter/togGround"),
    ("air", "AIR", "frmDesignList/frmFilter/togAir"),
    ("naval", "NAVAL", "frmDesignList/frmFilter/togNaval"),
    ("strategic", "STRATEGIC", "frmDesignList/frmFilter/togStrategic"),
)
_BUILD_PRIORITY_LABELS = ("HIGH", "MEDIUM", "LOW")
_BUILD_PRIORITY_VALUES = (100, 50, 1)
_QUEUE_PRIORITY_LABELS = ("HIGH", "MEDIUM", "LOW", "HOLD", "CANCEL")
_QUEUE_PRIORITY_VALUES = (100, 50, 1)
_QUEUE_PAGE_TABS = (
    ("queue", "QUEUE", 118.0, 46.0),
    ("foreign", "FOREIGN", 166.0, 56.0),
    ("deployments", "DEPLOY", 224.0, 54.0),
)
_DOMAIN_TOKENS = {
    "ground": ("land", "ground", "infantry", "tank", "artillery"),
    "air": ("air", "fighter", "aircraft", "bomber"),
    "naval": ("naval", "ship", "submarine", "fleet"),
    "strategic": ("strategic", "nuclear", "missile"),
}


class UnitProductionPanel:
    """Compose production controls into their source GML slots."""

    def __init__(self, open_design_cb=None):
        self._presenter = MilitaryPresenter()
        self._open_design_cb = open_design_cb
        self._category = "ground"
        self._selected_builder_country = ""
        self._selected_design_id = ""
        self._quantity = 50
        self._quantity_repeat = GMLValueRepeatPair()
        self._build_priority_index = 0
        self._right_page = "queue"
        self._queue_priority_overrides: dict[str, int] = {}

    def render(self, state, context: PanelRenderContext) -> bool:
        country_tag = str(context.target_tag or "").strip().upper()
        viewport = imgui.get_io().display_size
        if viewport.x <= 0 or viewport.y <= 0:
            viewport = imgui.get_main_viewport().size
        width, height = 842.0, 462.0
        x = max(0.0, (float(viewport.x) - width) / 2.0)
        y = max(0.0, (float(viewport.y) - height) / 2.0)

        designs = self._presenter.designs_for_country(state, country_tag)
        foreign_designs = self._presenter.foreign_designs_for_country(state, country_tag)
        builder_tags = self._builder_tags(country_tag, foreign_designs)
        if self._selected_builder_country not in builder_tags:
            self._selected_builder_country = country_tag

        with WindowManager.window(
            "UNIT PRODUCTION",
            x=x,
            y=y,
            w=width,
            h=height,
            test_id="unit_production.panel",
            gml_template=_GML_TEMPLATE,
        ) as is_open:
            if not is_open:
                return False

            ui = GMLWidgets(_ROOT)
            self._fit_right_pane_to_window(ui)
            production_list = ui.rect(_PRODUCTION_LIST_SLOT)
            production_row_width = None if production_list is None else production_list.width
            self._draw_source_frames(ui)
            self._render_category_filters(ui)
            self._render_builder_selector(
                state, country_tag, builder_tags, foreign_designs, ui, context,
            )
            visible_designs = self._visible_designs(
                country_tag, designs, foreign_designs,
            )
            selected_design = self._render_design_tree(visible_designs, ui)
            self._render_design_details(
                state, selected_design, country_tag, ui, context,
            )
            self._render_accept_foreign_toggle(state, country_tag, ui, context)
            self._render_right_page(
                state, country_tag, ui, context, production_row_width,
            )
            return True

    @staticmethod
    def _fit_right_pane_to_window(ui: GMLWidgets) -> None:
        session = active_gml_layout()
        if session is None:
            return
        right_path = ui.path("frmRight")
        right_rect = session.rect_for(right_path)
        available_width = session.window_size[0] - right_rect.x
        if available_width <= 0.0 or available_width >= right_rect.width:
            return

        # GML anchors this pane to the left, so compact viewports need a local squeeze to keep its controls reachable.
        session.scale_subtree_x(right_path, available_width / right_rect.width)

    @staticmethod
    def _draw_source_frames(ui: GMLWidgets) -> None:
        for frame in (
            "frmDesignList",
            "frmDesignList/frmFilter",
            "frmDesignList/frmDesignList",
            "frmDesignList/frmDesignList/frmList",
            "frmDesignList/frmDesignList/frmList/frmInner",
            "frmDesignList/frmInfo",
            "frmDesignList/frmUnitName",
            "frmDesignList/frmCost",
            "frmDesignList/frmCost/frmQty",
            "frmDesignList/frmEta",
            "frmRight",
            "frmRight/frmProduction",
        ):
            ui.frame(frame)

    def _render_category_filters(self, ui: GMLWidgets) -> None:
        for category, label, slot in _CATEGORIES:
            changed, _ = ui.toggle(
                slot,
                self._category == category,
                f"unit_production.category.{category}",
                icon=label,
                color=GAMETHEME.colors.info,
                tooltip=f"Show {label.lower()} unit designs",
            )
            if changed and self._category != category:
                self._category = category
                self._selected_design_id = ""

    def _render_builder_selector(
        self,
        state,
        country_tag: str,
        builder_tags: list[str],
        foreign_designs: list[dict],
        ui: GMLWidgets,
        context: PanelRenderContext,
    ) -> None:
        ui.text("frmDesignList/frmDesignList/lblProducer", "BUILD IN")
        country_names = self._country_names(state)
        labels = [
            f"{country_names.get(tag, tag)} ({tag})"
            for tag in builder_tags
        ]
        selected_index = builder_tags.index(self._selected_builder_country)
        slot = "frmDesignList/frmDesignList/cboCountry"
        imgui.begin_disabled(not context.is_own_country or len(builder_tags) <= 1)
        changed, selected_index = imgui.combo(
            "##unit-production-builder",
            selected_index,
            labels,
            test_id="unit_production.builder",
            gml_id=ui.path(slot),
        )
        imgui.end_disabled()
        if changed:
            self._selected_builder_country = builder_tags[selected_index]
            self._selected_design_id = ""

    def _visible_designs(
        self,
        country_tag: str,
        domestic_designs: list[dict],
        foreign_designs: list[dict],
    ) -> list[dict]:
        if self._selected_builder_country == country_tag:
            candidates = domestic_designs
        else:
            candidates = [
                row for row in foreign_designs
                if str(row.get("country_id") or "").strip().upper()
                == self._selected_builder_country
            ]
        return [
            row for row in candidates
            if self._design_category(row) == self._category
        ]

    @staticmethod
    def _design_category(row: dict) -> str:
        searchable = " ".join(
            str(row.get(key) or "")
            for key in ("domain", "branch", "class_name", "unit_type")
        ).casefold()
        for category in ("strategic", "naval", "air"):
            if any(token in searchable for token in _DOMAIN_TOKENS[category]):
                return category
        return "ground"

    def _render_design_tree(self, designs: list[dict], ui: GMLWidgets) -> dict | None:
        selected_design = next(
            (row for row in designs if str(row.get("id") or "") == self._selected_design_id),
            None,
        )
        if selected_design is None:
            self._selected_design_id = ""

        with gml_child_frame(
            ui.path(_DESIGN_TREE_SLOT),
            padding=(1.0, 1.0),
            bordered=False,
        ) as opened:
            if not opened:
                return selected_design
            if not designs:
                imgui.text_disabled(
                    "No designs are available for this category and builder.",
                    test_id="unit_production.designs.empty",
                )
                return None

            groups: dict[str, list[dict]] = {}
            for design in designs:
                group = str(
                    design.get("class_name")
                    or design.get("unit_type")
                    or design.get("branch")
                    or "Unit designs"
                ).replace("_", " ").title()
                groups.setdefault(group, []).append(design)

            imgui.push_style_var(imgui.StyleVar_.item_spacing, (1.0, 0.0))
            try:
                for group, rows in sorted(groups.items()):
                    group_id = group.casefold().replace(" ", "_")
                    tree_open = imgui.tree_node_ex(
                        f"{group}##unit-production-group-{group_id}",
                        imgui.TreeNodeFlags_.default_open,
                        test_id=f"unit_production.design_group.{group_id}",
                    )
                    if not tree_open:
                        continue
                    for row in rows:
                        is_selected = str(row.get("id") or "") == self._selected_design_id
                        design_id = str(row.get("id") or "")
                        display_name = str(
                            row.get("display_name") or row.get("name") or "Unit design"
                        )
                        clicked = imgui.selectable(
                            f"{UIPrimitives.fit_text(display_name, 164.0)}##unit-production-select-{design_id}",
                            is_selected,
                            size=(168.0, 15.0),
                            test_id=f"unit_production.select_design.{design_id}",
                        )[0]
                        imgui.same_line(0.0, 2.0)
                        show_details = (
                            self._open_design_cb is not None
                            and supports_design_details(row)
                        )
                        imgui.begin_disabled(not show_details)
                        try:
                            open_details = imgui.button(
                                f"INFO##unit-production-info-{design_id}",
                                (28.0, 15.0),
                                test_id=f"unit_production.view_design.{design_id}",
                            )
                        finally:
                            imgui.end_disabled()

                        if clicked:
                            self._selected_design_id = design_id
                            selected_design = row
                        if open_details and show_details:
                            self._open_design_cb(design_id)
                    imgui.tree_pop()
            finally:
                imgui.pop_style_var()
        return selected_design

    def _render_design_details(
        self,
        state,
        design: dict | None,
        country_tag: str,
        ui: GMLWidgets,
        context: PanelRenderContext,
    ) -> None:
        initial_production_eta_days = contribution_for(
            state, ClientPresentationKeys.INITIAL_PRODUCTION_ETA_DAYS,
        )
        name = str(
            (design or {}).get("display_name")
            or (design or {}).get("name")
            or "—"
        )
        class_name = str((design or {}).get("class_name") or "").casefold()
        unit_cost = self._number((design or {}).get("cost"))
        is_foreign_builder = self._selected_builder_country != country_tag
        can_edit = bool(context.is_own_country and context.net_client is not None)
        foreign_design = bool(
            design
            and is_foreign_builder
            and str(design.get("seller_accepts_orders")) in {"True", "true", "1"}
        )

        ui.text("frmDesignList/frmUnitName/lblUnitName", "DESIGN")
        ui.text(
            "frmDesignList/frmUnitName/txtUnitName",
            name if design else "—",
            test_id="unit_production.design_name",
        )
        ui.text("frmDesignList/frmInfo/lblPriority", "PRIORITY")
        priority_slot = "frmDesignList/frmInfo/cboPriority"
        priority_enabled = can_edit and design is not None and not is_foreign_builder
        imgui.begin_disabled(not priority_enabled)
        changed, priority_index = imgui.combo(
            "##unit-production-build-priority",
            min(self._build_priority_index, len(_BUILD_PRIORITY_LABELS) - 1),
            list(_BUILD_PRIORITY_LABELS),
            test_id="unit_production.build_priority",
            gml_id=ui.path(priority_slot),
        )
        imgui.end_disabled()
        if changed:
            self._build_priority_index = priority_index

        ui.text("frmDesignList/frmInfo/lblSpeed", "SPEED")
        speed_slot = "frmDesignList/frmInfo/cboSpeed"
        imgui.begin_disabled(True)
        imgui.combo(
            "##unit-production-speed",
            0,
            ["NORMAL", "FAST"],
            test_id="unit_production.speed",
            gml_id=ui.path(speed_slot),
        )
        imgui.end_disabled()
        if imgui.is_item_hovered(imgui.HoveredFlags_.allow_when_disabled):
            imgui.set_tooltip(
                "REFERENCE supports a Fast option, but OpenPower's production action has no speed field."
            )

        if class_name == "infantry":
            working_age_population = self._working_age_population(state, country_tag)
            ui.text(
                "frmDesignList/frmCost/lblTotalUnits",
                "POP. 15-64",
                tooltip="OpenPower working-age residents; this is not an enlistment allowance.",
            )
            ui.text(
                "frmDesignList/frmCost/txtUnitCost",
                "N/A" if working_age_population is None else self._format_count(working_age_population),
                tooltip=(
                    "OpenPower does not publish working-age population for this snapshot."
                    if working_age_population is None else
                    "Residents aged 15-64 in regions owned by this country. This value is not available recruitable manpower and does not cap the order."
                ),
                test_id="unit_production.manpower.value",
            )
        else:
            ui.text("frmDesignList/frmCost/lblUnitCost", "UNIT COST")
            ui.text(
                "frmDesignList/frmCost/txtUnitCost",
                self._format_money(unit_cost) if design else "—",
                tooltip="Unit cost from the selected unit design." if design else None,
            )
        ui.text("frmDesignList/frmCost/lblQty", "QUANTITY")
        quantity_slot = "frmDesignList/frmCost/frmQty/edtText"
        changed, quantity_text = imgui.input_text(
            "##unit-production-quantity",
            str(self._quantity),
            10,
            test_id="unit_production.quantity",
            gml_id=ui.path(quantity_slot),
        )
        if changed:
            self._quantity = self._parse_quantity(quantity_text, self._quantity)
            self._reset_quantity_repeat()

        # A one-step click lost REFERENCE's accelerated hold behavior; reuse the shared source cadence.
        quantity_actions = (
            ("btnDown", "−", "down", -1, "unit_production.quantity.down"),
            ("btnUp", "+", "up", 1, "unit_production.quantity.up"),
        )
        for control, glyph, repeat_key, direction, test_id in quantity_actions:
            slot = f"frmDesignList/frmCost/frmQty/{control}"
            clicked, active = ui.hitbox_state(
                slot,
                test_id,
                tooltip="Change by one; hold to repeat with increasing steps.",
            )
            self._advance_quantity_stepper(
                repeat_key,
                active,
                clicked,
                direction,
                float(imgui.get_time()),
            )
            ui.text_at(slot, glyph, offset=(-1.0, -3.0), max_width=10.0)

        total_cost = unit_cost * max(0, self._quantity)
        ui.text("frmDesignList/frmCost/lblTotalCost", "TOTAL COST")
        ui.text(
            "frmDesignList/frmCost/txtTotalCost",
            self._format_money(total_cost) if design else "—",
            tooltip=(
                f"Unit cost {self._format_money(unit_cost)} × {self._quantity}."
                if design else None
            ),
        )
        ui.text("frmDesignList/frmEta/lblEta", "ETA")
        if design is not None and not is_foreign_builder:
            eta_text = f"{initial_production_eta_days(_BUILD_PRIORITY_VALUES[self._build_priority_index])}d"
            eta_tooltip = (
                "Initial ETA from the domestic production action's selected priority. "
                "Capacity allocation will recalculate it during simulation."
            )
        elif design is not None:
            eta_text = "N/A"
            eta_tooltip = "The foreign producer sets its ETA after accepting the request."
        else:
            eta_text = "N/A"
            eta_tooltip = "Select a domestic design to preview the initial queue ETA."
        ui.text(
            "frmDesignList/frmEta/txtEta",
            eta_text,
            tooltip=eta_tooltip,
            test_id="unit_production.eta",
        )

        seller_accepts = foreign_design
        production_order_count = len(self._presenter.production_orders_for_country(state, country_tag))
        production_queue_full = production_order_count >= MAX_PRODUCTION_QUEUE_ORDERS
        can_build = bool(
            design
            and can_edit
            and self._quantity > 0
            and (not is_foreign_builder or seller_accepts)
            and (is_foreign_builder or not production_queue_full)
        )
        if not design:
            button_label = "BUILD"
            tooltip = "Select a design from the list first."
        elif is_foreign_builder and not seller_accepts:
            button_label = "REQUEST"
            tooltip = "This seller has not enabled foreign-order requests."
        elif is_foreign_builder:
            button_label = "REQUEST"
            tooltip = "Request this design from the selected foreign builder."
        elif production_queue_full:
            button_label = "ENROLL" if class_name == "infantry" else "BUILD"
            tooltip = f"The production queue is limited to {MAX_PRODUCTION_QUEUE_ORDERS} orders."
        else:
            button_label = "ENROLL" if class_name == "infantry" else "BUILD"
            tooltip = "Queue the selected design at the requested quantity."

        if ui.button(
            "frmDesignList/btnBuild",
            button_label,
            "unit_production.build",
            enabled=can_build,
            dynamic_enabled=True,
            tooltip=tooltip,
        ):
            if context.net_client is None or design is None:
                return
            if is_foreign_builder:
                context.net_client.send_action(ActionRequestForeignUnitOrder(
                    context.net_client.player_id,
                    country_tag,
                    self._selected_builder_country,
                    str(design.get("id") or ""),
                    self._quantity,
                ))
            else:
                context.net_client.send_action(ActionQueueUnitProduction(
                    context.net_client.player_id,
                    country_tag,
                    str(design.get("id") or ""),
                    self._quantity,
                    _BUILD_PRIORITY_VALUES[self._build_priority_index],
                ))

    def _advance_quantity_stepper(
        self,
        control: str,
        active: bool,
        clicked: bool,
        direction: int,
        now: float,
    ) -> None:
        updated, changed = self._quantity_repeat[control].advance(
            self._quantity,
            active=active,
            clicked=clicked,
            direction=direction,
            now=now,
            minimum=0,
            maximum=MAX_UNIT_PRODUCTION_QUANTITY,
        )
        if changed:
            self._quantity = updated

    def _reset_quantity_repeat(self) -> None:
        self._quantity_repeat.reset()

    def _render_accept_foreign_toggle(
        self,
        state,
        country_tag: str,
        ui: GMLWidgets,
        context: PanelRenderContext,
    ) -> None:
        table = state.tables.get("seller_acceptance_profiles")
        profile = None if table is None else next((
            row for row in table.to_dicts()
            if str(row.get("country_id") or "").strip().upper() == country_tag
        ), None)
        accepting = bool(profile and profile.get("accepts_foreign_orders"))
        ui.text(
            "frmRight/frmProduction/txtAcceptForeign",
            "ACCEPT FOREIGN",
            tooltip="Allow eligible countries to request unit production from you.",
            test_id="unit_production.accept_foreign.label",
        )
        changed, new_value = ui.toggle(
            "frmRight/frmProduction/togAcceptForeign",
            accepting,
            "unit_production.accept_foreign",
            icon="✓" if accepting else "",
            color=GAMETHEME.colors.positive,
            tooltip="Accept or decline incoming foreign production requests.",
            enabled=context.is_own_country and context.net_client is not None,
        )
        if changed and context.net_client is not None:
            context.net_client.send_action(ActionSetForeignOrderAcceptance(
                context.net_client.player_id,
                country_tag,
                new_value,
            ))

    def _render_right_page(
        self,
        state,
        country_tag: str,
        ui: GMLWidgets,
        context: PanelRenderContext,
        production_row_width: float | None,
    ) -> None:
        ui.text(
            "frmRight/frmProduction/lblTitle",
            "PRODUCTION QUEUE",
            test_id="unit_production.queue.title",
        )
        for page, label, offset, width in _QUEUE_PAGE_TABS:
            caption = f"[{label}]" if self._right_page == page else label
            if ui.button_at(
                "frmRight/frmProduction/lblTitle",
                caption,
                f"unit_production.page.{page}",
                offset=(offset, 0.0),
                size=(width, 15.0),
                padding=(1.0, 0.0),
            ):
                self._right_page = page

        if self._right_page == "queue":
            for slot, label in (
                ("frmRight/frmProduction/lblNbType", "QTY"),
                ("frmRight/frmProduction/lblNbType1", "FROM"),
                ("frmRight/frmProduction/lblNbType2", "TO"),
                ("frmRight/frmProduction/lblPriority", "PRIORITY"),
            ):
                ui.text(slot, label)
            ui.text_at(
                "frmRight/frmProduction/lblProgress",
                "PROGRESS",
                test_id="unit_production.queue.progress.heading",
            )

        with gml_child_frame(
            ui.path(_PRODUCTION_LIST_SLOT),
            padding=(1.0, 1.0),
            bordered=False,
        ) as opened:
            if not opened:
                return
            if self._right_page == "queue":
                self._render_production_queue(
                    state, country_tag, context, production_row_width,
                )
            elif self._right_page == "foreign":
                self._render_foreign_orders(state, country_tag, context)
            else:
                self._render_deployment_orders(state, country_tag, context)

        self._render_capacity(state, country_tag, ui)

    def _render_production_queue(
        self,
        state,
        country_tag: str,
        context: PanelRenderContext,
        row_width: float | None,
    ) -> None:
        orders = self._presenter.production_orders_for_country(state, country_tag)
        designs_table = state.tables.get("unit_designs")
        designs = {} if designs_table is None else {
            str(row.get("id") or ""): row for row in designs_table.to_dicts()
        }
        if not orders:
            imgui.text_disabled(
                "No production orders are queued.",
                test_id="unit_production.queue.empty",
            )
            return

        country_codes = self._country_codes(state)
        imgui.push_style_var(imgui.StyleVar_.item_spacing, (0.0, 0.0))
        try:
            for order in orders:
                design = designs.get(str(order.get("design_id") or ""), {})
                self._render_production_row(
                    order, design, country_codes, country_tag, context, row_width,
                )
        finally:
            imgui.pop_style_var()

    def _render_production_row(
        self,
        order: dict,
        design: dict,
        country_codes: dict[str, str],
        country_tag: str,
        context: PanelRenderContext,
        row_width: float | None,
    ) -> None:
        order_id = str(order.get("id") or "")
        quantity = max(0, int(order.get("quantity") or 0))
        progress = max(0.0, min(1.0, self._number(order.get("progress"))))
        status = str(order.get("status") or "queued").strip().casefold()
        design_name = str(
            design.get("display_name")
            or order.get("design_id")
            or "Unknown design"
        )
        design_category = self._design_category(design) if design else "ground"
        icon = {"ground": "G", "air": "A", "naval": "N", "strategic": "S"}[design_category]
        order_country = str(order.get("country_id") or country_tag).strip().upper()
        country_code = country_codes.get(order_country, order_country[:3])
        eta = int(order.get("eta_days") or -1)
        eta_text = "N/A" if eta < 0 else f"{eta}d"
        priority = self._queue_priority_overrides.get(
            order_id,
            max(1, int(order.get("priority") or 1)),
        )
        priority_index = self._queue_priority_index(priority, status)
        priority_color = self._priority_color(priority_index)

        row_start = imgui.get_cursor_screen_pos()
        row_draw = imgui.get_window_draw_list()
        effective_row_width = 522.0 if row_width is None else min(522.0, row_width)
        row_draw.add_rect_filled(
            (float(row_start.x), float(row_start.y)),
            (float(row_start.x) + effective_row_width, float(row_start.y) + 18.0),
            imgui.get_color_u32((priority_color[0], priority_color[1], priority_color[2], 0.22)),
        )
        with gml_row("lstUnitProductionItem", order_id, width=effective_row_width) as row_ui:
            row_ui.text_at(
                "picType", icon, offset=(6.0, 1.0), max_width=12.0,
                color=GAMETHEME.colors.text_main,
            )
            row_ui.text(
                "txtQty", f"×{quantity}",
                test_id=f"unit_production.queue.quantity.{order_id}",
            )
            row_ui.text(
                "txtUnit", design_name,
                tooltip=design_name,
                test_id=f"unit_production.queue.design.{order_id}",
            )
            row_ui.text("txtCodeFrom", country_code)
            row_ui.text("txtCodeTo", country_code)
            row_ui.meter("frmProgress", progress, GAMETHEME.colors.positive)
            row_ui.text_at(
                "frmProgress", eta_text,
                offset=(6.0, 1.0), max_width=148.0,
                color=GAMETHEME.colors.text_main,
                tooltip=str(order.get("blocking_reason") or eta_text),
                test_id=f"unit_production.queue.progress.{order_id}",
            )
            imgui.begin_disabled(
                not context.is_own_country or context.net_client is None
                or status not in {"queued", "paused"}
            )
            changed, selected_index = imgui.combo(
                f"##unit-production-order-priority-{order_id}",
                priority_index,
                list(_QUEUE_PRIORITY_LABELS),
                test_id=f"unit_production.queue.priority.{order_id}",
                gml_id=row_ui.path("cboPriority"),
            )
            imgui.end_disabled()
            if changed:
                self._apply_queue_priority_choice(
                    order, selected_index, context,
                )

        reason = str(order.get("blocking_reason") or "")
        if reason and imgui.is_item_hovered():
            imgui.set_tooltip(reason)

    def _apply_queue_priority_choice(
        self,
        order: dict,
        selected_index: int,
        context: PanelRenderContext,
    ) -> None:
        if context.net_client is None:
            return
        order_id = str(order.get("id") or "")
        if selected_index == 4:
            context.net_client.send_action(ActionCancelProductionOrder(
                context.net_client.player_id,
                order_id,
            ))
            return
        if selected_index == 3:
            context.net_client.send_action(ActionSetProductionPaused(
                context.net_client.player_id,
                order_id,
                True,
            ))
            self._queue_priority_overrides[order_id] = max(
                1, int(order.get("priority") or 1),
            )
            return

        priority = _QUEUE_PRIORITY_VALUES[selected_index]
        if str(order.get("status") or "").casefold() == "paused":
            context.net_client.send_action(ActionSetProductionPaused(
                context.net_client.player_id,
                order_id,
                False,
            ))
        context.net_client.send_action(ActionSetProductionPriority(
            context.net_client.player_id,
            order_id,
            priority,
        ))
        self._queue_priority_overrides[order_id] = priority

    def _render_foreign_orders(self, state, country_tag: str, context: PanelRenderContext) -> None:
        foreign_designs = self._presenter.foreign_designs_for_country(state, country_tag)
        foreign_orders = self._presenter.foreign_orders_for_country(state, country_tag)
        imgui.text_colored(GAMETHEME.colors.text_main, "ELIGIBLE FOREIGN DESIGNS")
        if not foreign_designs:
            imgui.text_disabled(
                "No foreign designs are eligible for inspection.",
                test_id="unit_production.foreign.empty",
            )
        else:
            for row in foreign_designs:
                design_id = str(row.get("id") or "")
                seller = str(row.get("country_id") or "").strip().upper()
                name = str(row.get("display_name") or design_id or "Unit design")
                accepts = bool(row.get("seller_accepts_orders"))
                imgui.text(UIPrimitives.fit_text(f"{name} · {seller}", 260.0))
                imgui.same_line()
                imgui.text_disabled(self._format_money(self._number(row.get("cost"))))
                imgui.same_line()
                imgui.begin_disabled(not context.is_own_country or not accepts or context.net_client is None)
                try:
                    requested = imgui.button(
                        f"REQUEST ×{max(1, self._quantity)}##{design_id}",
                        (132.0, 16.0),
                        test_id=f"unit_production.foreign.request.{design_id}",
                    )
                finally:
                    imgui.end_disabled()
                if requested and context.net_client is not None:
                    context.net_client.send_action(ActionRequestForeignUnitOrder(
                        context.net_client.player_id,
                        country_tag,
                        seller,
                        design_id,
                        max(1, self._quantity),
                    ))
                if not accepts:
                    imgui.text_disabled("Seller has not enabled foreign requests.")

        imgui.separator()
        imgui.text_colored(GAMETHEME.colors.text_main, "FOREIGN CONTRACTS")
        if not foreign_orders:
            imgui.text_disabled(
                "No foreign unit contracts are active or recently completed.",
                test_id="unit_production.contracts.empty",
            )
        for row in foreign_orders:
            self._render_foreign_contract(row, country_tag, context)

    def _render_foreign_contract(
        self,
        row: dict,
        country_tag: str,
        context: PanelRenderContext,
    ) -> None:
        order_id = str(row.get("id") or "")
        buyer = str(row.get("buyer_country_id") or "").strip().upper()
        seller = str(row.get("seller_country_id") or "").strip().upper()
        status = str(row.get("status") or "unknown").strip().casefold()
        name = str(row.get("design_name") or row.get("design_id") or "Unit design")
        quantity = max(0, int(row.get("quantity") or 0))
        imgui.text(UIPrimitives.fit_text(
            f"{name} ×{quantity} · {status.replace('_', ' ').title()}", 480.0,
        ))
        imgui.text_disabled(UIPrimitives.fit_text(
            f"Buyer {buyer} · Seller {seller} · {self._format_money(self._number(row.get('price')))}",
            480.0,
        ))
        if not context.is_own_country or context.net_client is None:
            return

        can_respond = seller == country_tag and status == "pending_seller_acceptance"
        if can_respond:
            if imgui.button(
                f"ACCEPT##{order_id}",
                (72.0, 16.0),
                test_id=f"unit_production.foreign.accept.{order_id}",
            ):
                context.net_client.send_action(ActionRespondForeignUnitOrder(
                    context.net_client.player_id, order_id, True,
                ))
            imgui.same_line()
            if imgui.button(
                f"REJECT##{order_id}",
                (72.0, 16.0),
                test_id=f"unit_production.foreign.reject.{order_id}",
            ):
                context.net_client.send_action(ActionRespondForeignUnitOrder(
                    context.net_client.player_id, order_id, False,
                ))
            imgui.same_line()

        if status in {"pending_seller_acceptance", "accepted", "in_production"}:
            if imgui.button(
                f"CANCEL CONTRACT##{order_id}",
                (132.0, 16.0),
                test_id=f"unit_production.foreign.cancel.{order_id}",
            ):
                context.net_client.send_action(ActionCancelForeignUnitOrder(
                    context.net_client.player_id, order_id,
                ))

    def _render_deployment_orders(
        self,
        state,
        country_tag: str,
        context: PanelRenderContext,
    ) -> None:
        rows = self._presenter.deployment_orders_for_country(state, country_tag)
        if not rows:
            imgui.text_disabled(
                "Completed groups will appear here until dispatched.",
                test_id="unit_production.deployments.empty",
            )
            return

        for row in rows:
            order_id = str(row.get("id") or "")
            unit_id = str(row.get("unit_id") or "")
            quantity = max(0, int(row.get("quantity") or 0))
            status = str(row.get("status") or "queued")
            description = (
                f"{row.get('unit_type', 'unit')} ×{quantity} · {status} · "
                f"{row.get('origin_name', 'unknown')} → "
                f"{row.get('destination_name', 'choose destination')}"
            )
            imgui.text(UIPrimitives.fit_text(description, 525.0))
            reason = str(row.get("blocking_reason") or "")
            if reason:
                imgui.text_disabled(UIPrimitives.fit_text(reason, 525.0))

            dispatchable = status.casefold() in {"queued", "blocked"}
            can_dispatch = bool(
                context.is_own_country
                and context.net_client is not None
                and context.selected_region_id is not None
                and dispatchable
            )
            if can_dispatch:
                if imgui.button(
                    f"DISPATCH TO SELECTED REGION##{order_id}",
                    (220.0, 17.0),
                    test_id=f"unit_production.deployments.dispatch.{order_id}",
                ):
                    context.net_client.send_action(ActionDispatchUnitDeployment(
                        context.net_client.player_id,
                        unit_id,
                        int(context.selected_region_id),
                        0,
                    ))
                if quantity > 1:
                    imgui.same_line()
                    if imgui.button(
                        f"SPLIT HALF##{order_id}",
                        (104.0, 17.0),
                        test_id=f"unit_production.deployments.split.{order_id}",
                    ):
                        context.net_client.send_action(ActionDispatchUnitDeployment(
                            context.net_client.player_id,
                            unit_id,
                            int(context.selected_region_id),
                            max(1, quantity // 2),
                        ))
            imgui.separator()

    def _render_capacity(self, state, country_tag: str, ui: GMLWidgets) -> None:
        ratio = self._capacity_ratio(state, country_tag)
        ui.text(
            "frmRight/frmProduction/lblUnitName",
            "CAPACITY",
            tooltip="OpenPower production capacity is calculated from current order allocations.",
        )
        ui.text(
            "frmRight/frmProduction/txtValue",
            "N/A" if ratio is None else f"{ratio:.0%}",
            right=True,
            test_id="unit_production.capacity.value",
            tooltip=(
                "No authoritative aggregate capacity ratio is present in this snapshot."
                if ratio is None else "Allocated production capacity as a share of annual capacity."
            ),
        )
        ui.meter(
            "frmRight/frmProduction/frmCapacity",
            0.0 if ratio is None else ratio,
            GAMETHEME.colors.positive if ratio is not None else GAMETHEME.colors.text_dim,
        )

    _capacity_ratio = staticmethod(production_snapshot.capacity_ratio)
    _working_age_population = staticmethod(production_snapshot.working_age_population)

    @staticmethod
    def _builder_tags(country_tag: str, foreign_designs: list[dict]) -> list[str]:
        tags = {country_tag} if country_tag else set()
        tags.update(
            str(row.get("country_id") or "").strip().upper()
            for row in foreign_designs
            if str(row.get("country_id") or "").strip()
        )
        return ([country_tag] if country_tag in tags else []) + sorted(tags - {country_tag})

    @staticmethod
    def _country_names(state) -> dict[str, str]:
        table = state.tables.get("countries")
        if table is None:
            return {}
        return {
            str(row.get("id") or "").strip().upper(): str(row.get("name") or row.get("id") or "")
            for row in table.to_dicts()
        }

    @staticmethod
    def _country_codes(state) -> dict[str, str]:
        table = state.tables.get("countries")
        if table is None:
            return {}
        return {
            str(row.get("id") or "").strip().upper(): str(
                row.get("code") or row.get("id") or ""
            ).strip().upper()[:3]
            for row in table.to_dicts()
        }

    @staticmethod
    def _queue_priority_index(priority: int, status: str) -> int:
        if status == "paused":
            return 3
        if priority >= 75:
            return 0
        if priority >= 25:
            return 1
        return 2

    @staticmethod
    def _priority_color(priority_index: int) -> tuple[float, float, float, float]:
        return {
            0: (0.91, 0.39, 0.39, 1.0),
            1: (0.86, 0.83, 0.42, 1.0),
            2: (0.18, 0.43, 0.60, 1.0),
            3: (0.62, 0.62, 0.62, 1.0),
        }.get(priority_index, (0.25, 0.27, 0.3, 1.0))

    _number = staticmethod(production_snapshot.nonnegative_number)

    @staticmethod
    def _parse_quantity(value: str, fallback: int) -> int:
        digits = "".join(character for character in str(value) if character.isdigit())
        if not digits:
            return fallback
        return min(MAX_UNIT_PRODUCTION_QUANTITY, max(0, int(digits)))

    @staticmethod
    def _format_money(value: float) -> str:
        return format_currency(max(0.0, value))

    @staticmethod
    def _format_count(value: int) -> str:
        return f"{max(0, int(value)):,}".replace(",", " ")
