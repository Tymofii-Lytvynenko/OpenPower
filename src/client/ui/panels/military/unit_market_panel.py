from __future__ import annotations

from collections.abc import Sequence

from src.client.services.client_presentation import contribution_for
from src.client.ui.components.shared.gml_value_repeat import GMLValueRepeatPair
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.formatting import format_currency
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.gml_layout import active_gml_layout
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.military.unit_design_widgets import (
    DESIGN_METRICS,
    saved_capabilities,
)
from src.client.ui.panels.military.unit_type_options import (
    UnitTypeOption,
    unit_type_options_for_roles,
)
from src.client.ui.panels.shared.panel_widgets import draw_empty_state
from src.shared.actions import ActionBuyMarketUnit
from src.shared.mod_api import ClientPresentationKeys

_ROOT = "Unit_Buy_Used_Window"
_LIST_SLOT = "frmBorder/frmInner/frmDesignList"
_LIST_ROOT = f"{_ROOT}/{_LIST_SLOT}"
_DESIGN_SLOT = "frmDesignView"
_DESIGN_ROOT = f"{_ROOT}/{_DESIGN_SLOT}"
_CAPABILITIES_ROOT = f"{_DESIGN_ROOT}/frmUnitSpecs/frmList/frmInner"


class UnitMarketPanel:
    """Browse eligible used-unit listings in the source GML window."""

    def __init__(self) -> None:
        self._presenter = MilitaryPresenter()
        self._selected_role = ""
        self._selected_listing_id = ""
        self._quantity = 0
        self._quantity_edit_text = ""
        self._quantity_editing = False
        self._quantity_cursor_pos = 0
        self._quantity_selection_start = 0
        self._quantity_selection_end = 0
        self._request_sent = False
        self._quantity_repeat = GMLValueRepeatPair()

    def render(self, state, context: PanelRenderContext) -> bool:
        viewport = imgui.get_io().display_size
        if viewport.x <= 0 or viewport.y <= 0:
            viewport = imgui.get_main_viewport().size
        width, height = 712.0, 472.0
        x = max(0.0, (float(viewport.x) - width) / 2.0)
        y = max(0.0, (float(viewport.y) - height) / 2.0)
        country_tag = str(context.target_tag or "").strip().upper()
        listings = self._presenter.market_listings_for_country(state, country_tag)
        designs = self._designs_by_id(state)
        role_by_listing = {
            str(row.get("id") or ""): self._listing_role(row, designs, state)
            for row in listings
        }
        role_options = unit_type_options_for_roles(
            (role for role in role_by_listing.values() if role),
            state,
        )
        roles = [option.role for option in role_options]
        if self._selected_role not in roles:
            self._selected_role = roles[0] if roles else ""

        flags = 0
        with WindowManager.window(
            "USED UNIT MARKET",
            x=x,
            y=y,
            w=width,
            h=height,
            flags=flags,
            test_id="unit_market.panel",
            gml_template="Unit_Buy_Used_Window",
        ) as is_open:
            if not is_open:
                return False

            ui = GMLWidgets(_ROOT)
            self._draw_source_frames(ui)
            self._render_type_selector(ui, roles, role_options)
            visible_listings = [
                row for row in listings
                if role_by_listing.get(str(row.get("id") or "")) == self._selected_role
            ]
            selected = self._render_listing_list(ui, visible_listings)
            self._render_selection(ui, selected, designs, context)
            self._render_capabilities(ui, selected, designs, state)
            return True

    @staticmethod
    def _designs_by_id(state) -> dict[str, dict]:
        table = getattr(state, "tables", {}).get("unit_designs")
        if table is None or table.is_empty() or "id" not in table.columns:
            return {}
        return {str(row.get("id") or ""): row for row in table.to_dicts()}

    @staticmethod
    def _listing_role(listing: dict, designs: dict[str, dict], state) -> str:
        canonical_role = contribution_for(state, ClientPresentationKeys.CANONICAL_ROLE)
        design = designs.get(str(listing.get("design_id") or ""), {})
        role = design.get("class_name") or listing.get("unit_type")
        return canonical_role(role) if role else ""

    @staticmethod
    def _draw_source_frames(ui: GMLWidgets) -> None:
        for frame in (
            "frmBorder/frmInner",
            "frmBorder/frmInner/frmDesignList",
            "frmDesignView",
            "frmDesignView/frm3dModel",
            "frmDesignView/frmUnitSpecs",
        ):
            ui.frame(frame)

    def _render_type_selector(
        self,
        ui: GMLWidgets,
        roles: list[str],
        role_options: Sequence[UnitTypeOption],
    ) -> None:
        ui.text(f"{_LIST_SLOT}/lblUnitType", "UNIT TYPE")
        labels = [option.label for option in role_options] or ["No eligible unit types"]
        selected_index = roles.index(self._selected_role) if self._selected_role in roles else 0
        imgui.begin_disabled(not roles)
        imgui.push_style_var(imgui.StyleVar_.frame_padding, (4.0, 2.0))
        changed, selected_index = imgui.combo(
            "##unit_market.type",
            selected_index,
            labels,
            test_id="unit_market.type",
            gml_id=f"{_LIST_ROOT}/cboUnitType",
        )
        imgui.pop_style_var()
        imgui.end_disabled()
        if changed and roles:
            self._selected_role = roles[selected_index]
            self._selected_listing_id = ""
            self._quantity = 0
            self._quantity_edit_text = ""
            self._quantity_editing = False
            self._request_sent = False
            self._reset_quantity_repeat()

    def _render_listing_list(self, ui: GMLWidgets, listings: list[dict]) -> dict | None:
        selected = next(
            (row for row in listings if str(row.get("id") or "") == self._selected_listing_id),
            None,
        )
        if selected is None:
            self._selected_listing_id = ""
            self._quantity = 0
            self._quantity_edit_text = ""
            self._quantity_editing = False
            self._request_sent = False
            self._reset_quantity_repeat()

        opened = imgui.begin_child(
            "unit_market.list",
            (268.0, 287.0),
            child_flags=imgui.ChildFlags_.borders,
            test_id="unit_market.list",
            gml_id=f"{_LIST_ROOT}/lstUnits",
        )
        if opened:
            if not listings:
                draw_empty_state("No eligible used units are listed for this type.")
            for row in listings:
                listing_id = str(row.get("id") or "")
                design_name = str(row.get("design_name") or "Unit design")
                quantity = max(0, int(row.get("quantity") or 0))
                label = f"{quantity:,}  {design_name}".replace(",", " ")
                if imgui.selectable(
                    f"{label}##{listing_id}",
                    listing_id == self._selected_listing_id,
                    size=(0.0, 15.0),
                    test_id=f"unit_market.listing.{listing_id}",
                )[0]:
                    if listing_id != self._selected_listing_id:
                        self._selected_listing_id = listing_id
                        self._quantity = quantity
                        self._quantity_edit_text = str(quantity)
                        self._quantity_editing = False
                        self._request_sent = False
                        self._reset_quantity_repeat()
                    selected = row
        imgui.end_child()
        return selected

    def _render_selection(
        self,
        ui: GMLWidgets,
        listing: dict | None,
        designs: dict[str, dict],
        context: PanelRenderContext,
    ) -> None:
        design = designs.get(str((listing or {}).get("design_id") or ""), {})
        available = max(0, int((listing or {}).get("quantity") or 0))
        if listing is None:
            seller = "—"
            design_name = "—"
            unit_price = 0.0
            self._quantity = 0
        else:
            seller = str(listing.get("seller_name") or listing.get("seller_country_id") or "Unknown")
            design_name = str(listing.get("design_name") or design.get("display_name") or "Unit design")
            unit_price = max(0.0, float(listing.get("price") or 0.0))
            self._quantity = min(max(1, self._quantity or available), available)

        ui.text(f"{_LIST_SLOT}/lblProvider", "PROVIDER")
        self._render_value_field(ui, f"{_LIST_SLOT}/edtUnitName", seller, "unit_market.seller")
        ui.text(f"{_LIST_SLOT}/lblUnitCost", "UNIT PRICE")
        self._render_value_field(
            ui, f"{_LIST_SLOT}/edtUnitName1",
            self._format_money(unit_price) if listing else "—",
            "unit_market.unit_price",
        )
        ui.text(f"{_LIST_SLOT}/lblQty", "QUANTITY")
        self._render_quantity(ui, listing, available)
        ui.text(f"{_LIST_SLOT}/lblUnitName2", "TOTAL PRICE")
        total = unit_price * self._quantity if listing else 0.0
        self._render_value_field(
            ui, f"{_LIST_SLOT}/edtUnitName2",
            self._format_money(total) if listing else "—",
            "unit_market.total_price",
        )

        ui.text(f"{_DESIGN_SLOT}/frmUnitName/lblUnitName", "DESIGN")
        self._render_value_field(
            ui, f"{_DESIGN_SLOT}/frmUnitName/edtUnitName",
            design_name,
            "unit_market.design_name",
        )
        imgui.text_wrapped(
            "3D model preview is unavailable. Capability values below use OpenPower units and scales.",
            gml_id=f"{_DESIGN_ROOT}/frm3dModel/lblDescription",
            test_id="unit_market.preview_unavailable",
        )

        quantity_valid = listing is not None and 1 <= self._quantity <= available
        can_buy = bool(
            context.is_own_country
            and context.net_client is not None
            and quantity_valid
            and not self._request_sent
        )
        tooltip = None
        if not context.is_own_country:
            tooltip = "Purchases are available only for your country."
        elif context.net_client is None:
            tooltip = "Connect to the game before purchasing a used unit."
        elif listing is None:
            tooltip = "Select an eligible listing first."
        elif not quantity_valid:
            tooltip = "Choose a quantity available in this listing."
        elif self._request_sent:
            tooltip = "The server is validating this purchase request."
        if ui.button(
            f"{_LIST_SLOT}/btnBuy",
            "BUY UNIT",
            "unit_market.buy",
            enabled=can_buy,
            dynamic_enabled=True,
            tooltip=tooltip,
        ):
            context.net_client.send_action(ActionBuyMarketUnit(
                context.net_client.player_id,
                str(listing.get("id") or ""),
                str(context.target_tag or "").strip().upper(),
                self._quantity,
            ))
            self._request_sent = True

        if self._request_sent and listing is not None:
            ui.text_at(
                f"{_LIST_SLOT}/btnBuy",
                "REQUEST SENT",
                offset=(92.0, 3.0),
                max_width=92.0,
                color=GAMETHEME.colors.positive,
                tooltip="The server validates the current listing and available funds.",
                test_id="unit_market.request_status",
            )

    @staticmethod
    def _render_value_field(ui: GMLWidgets, slot: str, value: str, test_id: str) -> None:
        imgui.push_style_var(imgui.StyleVar_.frame_padding, (3.0, 2.0))
        try:
            imgui.input_text(
                f"##{test_id}",
                value,
                flags=imgui.InputTextFlags_.read_only,
                test_id=test_id,
                gml_id=ui.path(slot),
            )
        finally:
            imgui.pop_style_var()

    def _render_quantity(
        self,
        ui: GMLWidgets,
        listing: dict | None,
        available: int,
    ) -> None:
        field_slot = f"{_LIST_SLOT}/frmUpdatableValue1/edtText"
        field = f"{_LIST_ROOT}/frmUpdatableValue1/edtText"
        was_editing = self._quantity_editing
        display_text = (
            self._quantity_edit_text
            if was_editing
            else str(self._quantity) if listing is not None else ""
        )
        enter_key_pressed = (
            imgui.is_key_pressed(imgui.Key.enter, False)
            or imgui.is_key_pressed(imgui.Key.keypad_enter, False)
        )
        escape_key_pressed = imgui.is_key_pressed(imgui.Key.escape, False)
        imgui.begin_disabled(listing is None or available <= 0)
        imgui.push_style_var(imgui.StyleVar_.frame_padding, (2.0, 2.0))
        transparent = (0.0, 0.0, 0.0, 0.0)
        imgui.push_style_color(imgui.Col_.text, transparent)
        imgui.push_style_color(imgui.Col_.text_selected_bg, transparent)
        try:
            changed, edit_text = imgui.input_text(
                "##unit_market.quantity",
                display_text,
                imgui.InputTextFlags_.callback_char_filter
                | imgui.InputTextFlags_.enter_returns_true
                | imgui.InputTextFlags_.callback_always,
                test_id="unit_market.quantity.input",
                gml_id=field,
                callback=self._capture_quantity_cursor,
            )
        finally:
            imgui.pop_style_color(2)
            imgui.pop_style_var()
        imgui.end_disabled()

        input_focused = imgui.is_item_focused()
        input_active = imgui.is_item_active()
        input_hovered = imgui.is_item_hovered()
        input_activated = imgui.is_item_activated()
        input_deactivated = imgui.is_item_deactivated()
        enter_pressed = was_editing and input_focused and enter_key_pressed
        escape_pressed = was_editing and escape_key_pressed
        if not escape_pressed and (input_active or input_focused or changed):
            # EnterReturnsTrue suppresses the edit return value until Enter, so keep the
            # live buffer while focused and preserve it if Escape restores ImGui's old value.
            self._quantity_edit_text = edit_text.strip()
        if enter_pressed or escape_pressed:
            # REFERENCE returns focus to the owning value control; moving to the next focusable
            # item prevents ImGui's Enter/Escape handling from leaving a live text editor.
            self._commit_quantity_text(available)
            imgui.set_keyboard_focus_here(0)
        elif input_active or input_activated:
            self._quantity_editing = True
            if not was_editing:
                if not changed:
                    self._quantity_edit_text = str(self._quantity)
        elif was_editing and (input_deactivated or not input_focused):
            self._commit_quantity_text(available)
        elif input_focused:
            self._quantity_editing = True
            if not was_editing and not changed:
                self._quantity_edit_text = str(self._quantity)
        elif changed:
            self._commit_quantity_text(available)
        elif not self._quantity_editing:
            self._quantity_edit_text = str(self._quantity)

        if listing is not None:
            self._draw_quantity_mask(ui, field_slot, input_active, input_hovered)
        if self._quantity_editing:
            self._draw_quantity_selection(ui, field_slot, self._quantity_edit_text)
            self._draw_quantity_text(
                ui,
                field_slot,
                self._quantity_edit_text,
                test_id="unit_market.quantity.edit_display",
            )
            if input_active:
                self._draw_quantity_caret(ui, field_slot, self._quantity_edit_text)
        elif listing is not None:
            self._draw_quantity_text(
                ui,
                field_slot,
                self._format_quantity(self._quantity),
                test_id="unit_market.quantity.display",
            )

        if changed:
            self._request_sent = False
            self._reset_quantity_repeat()

        down_clicked, down_active = ui.hitbox_state(
            f"{_LIST_SLOT}/frmUpdatableValue1/btnDown",
            "unit_market.quantity.down",
            enabled=listing is not None and available > 0,
            tooltip="Decrease by one; hold to repeat with increasing steps.",
        )
        self._advance_quantity_arrow("down", down_active, down_clicked, -1, available)
        self._draw_quantity_arrow(
            ui, f"{_LIST_SLOT}/frmUpdatableValue1/btnDown", down=True,
            enabled=listing is not None and available > 0,
        )

        up_clicked, up_active = ui.hitbox_state(
            f"{_LIST_SLOT}/frmUpdatableValue1/btnUp",
            "unit_market.quantity.up",
            enabled=listing is not None and available > 0,
            tooltip="Increase by one; hold to repeat with increasing steps.",
        )
        self._advance_quantity_arrow("up", up_active, up_clicked, 1, available)
        self._draw_quantity_arrow(
            ui, f"{_LIST_SLOT}/frmUpdatableValue1/btnUp", down=False,
            enabled=listing is not None and available > 0,
        )

    def _advance_quantity_arrow(
        self,
        control: str,
        active: bool,
        clicked: bool,
        direction: int,
        available: int,
    ) -> None:
        updated, changed = self._quantity_repeat[control].advance(
            self._quantity,
            active=active,
            clicked=clicked,
            direction=direction,
            now=float(imgui.get_time()),
            minimum=1,
            maximum=max(1, available),
        )
        if changed:
            self._quantity = updated
            self._request_sent = False

    def _reset_quantity_repeat(self) -> None:
        self._quantity_repeat.reset()

    def _commit_quantity_text(self, available: int) -> None:
        try:
            requested = int(self._quantity_edit_text.strip() or "0")
        except ValueError:
            requested = 0
        self._quantity = min(max(1, requested), max(1, available))
        self._quantity_edit_text = str(self._quantity)
        self._quantity_editing = False
        self._request_sent = False
        self._reset_quantity_repeat()

    @staticmethod
    def _format_quantity(value: int) -> str:
        return f"{int(value):,}".replace(",", " ")

    def _capture_quantity_cursor(self, data) -> int:
        if int(data.event_flag) == int(imgui.InputTextFlags_.callback_char_filter):
            character = int(data.event_char)
            return 0 if ord("0") <= character <= ord("9") else 1
        self._quantity_cursor_pos = max(0, int(data.cursor_pos))
        self._quantity_selection_start = max(0, int(data.selection_start))
        self._quantity_selection_end = max(0, int(data.selection_end))
        return 0

    @staticmethod
    def _quantity_text_geometry(rect, value: str) -> tuple[float, float, float]:
        text_size = imgui.calc_text_size(value)
        text_width = min(float(text_size.x), max(0.0, rect.width - 6.0))
        x_offset = max(3.0, rect.width - text_width - 3.0)
        y_offset = max(0.0, (rect.height - float(text_size.y)) / 2.0)
        return x_offset, y_offset, text_width

    @staticmethod
    def _blend_color(foreground: tuple, background: tuple) -> tuple[float, float, float, float]:
        alpha = foreground[3]
        return tuple(
            foreground[index] * alpha + background[index] * (1.0 - alpha)
            for index in range(3)
        ) + (1.0,)

    def _draw_quantity_mask(
        self,
        ui: GMLWidgets,
        field_slot: str,
        input_active: bool,
        input_hovered: bool,
    ) -> None:
        session = active_gml_layout()
        rect = ui.rect(field_slot)
        if session is None or rect is None or rect.width <= 2.0 or rect.height <= 2.0:
            return

        # ImGui's native editor is left-aligned; repaint its text before drawing the REFERENCE right-aligned value and cursor.
        window_bg = GAMETHEME.colors.bg_window
        panel_bg = self._blend_color(GAMETHEME.colors.panel_bg_dark, window_bg)
        frame_color = (
            GAMETHEME.colors.pressed_neutral if input_active
            else GAMETHEME.colors.hover_neutral if input_hovered
            else GAMETHEME.colors.bg_input
        )
        interior_color = self._blend_color(frame_color, panel_bg)
        x = session.window_position[0] + rect.x - imgui.get_scroll_x()
        y = session.window_position[1] + rect.y - imgui.get_scroll_y()
        imgui.get_window_draw_list().add_rect_filled(
            (x + 1.0, y + 1.0),
            (x + rect.width - 1.0, y + rect.height - 1.0),
            imgui.get_color_u32(interior_color),
        )

    def _draw_quantity_text(
        self,
        ui: GMLWidgets,
        field_slot: str,
        value: str,
        *,
        test_id: str,
    ) -> None:
        rect = ui.rect(field_slot)
        if rect is None or not value:
            return
        x_offset, y_offset, text_width = self._quantity_text_geometry(rect, value)
        ui.text_at(
            field_slot,
            value,
            offset=(x_offset, y_offset),
            max_width=text_width,
            test_id=test_id,
        )

    def _draw_quantity_selection(self, ui: GMLWidgets, field_slot: str, value: str) -> None:
        start = min(self._quantity_selection_start, self._quantity_selection_end, len(value))
        end = min(max(self._quantity_selection_start, self._quantity_selection_end), len(value))
        if start == end:
            return
        session = active_gml_layout()
        rect = ui.rect(field_slot)
        if session is None or rect is None:
            return
        x_offset, y_offset, _ = self._quantity_text_geometry(rect, value)
        start_x = x_offset + float(imgui.calc_text_size(value[:start]).x)
        end_x = x_offset + float(imgui.calc_text_size(value[:end]).x)
        x = session.window_position[0] + rect.x - imgui.get_scroll_x()
        y = session.window_position[1] + rect.y - imgui.get_scroll_y()
        selection = (*GAMETHEME.colors.accent[:3], 0.42)
        imgui.get_window_draw_list().add_rect_filled(
            (x + start_x, y + y_offset),
            (x + end_x, y + y_offset + float(imgui.calc_text_size(value).y)),
            imgui.get_color_u32(selection),
        )

    def _draw_quantity_caret(self, ui: GMLWidgets, field_slot: str, value: str) -> None:
        session = active_gml_layout()
        rect = ui.rect(field_slot)
        if session is None or rect is None:
            return
        cursor_pos = min(self._quantity_cursor_pos, len(value))
        x_offset, y_offset, _ = self._quantity_text_geometry(rect, value)
        cursor_x = x_offset + float(imgui.calc_text_size(value[:cursor_pos]).x)
        x = session.window_position[0] + rect.x - imgui.get_scroll_x() + cursor_x
        y = session.window_position[1] + rect.y - imgui.get_scroll_y() + y_offset
        height = float(imgui.calc_text_size(value).y)
        imgui.get_window_draw_list().add_line(
            (x, y),
            (x, y + height),
            imgui.get_color_u32(GAMETHEME.colors.text_main),
            1.0,
        )

    @staticmethod
    def _draw_quantity_arrow(ui: GMLWidgets, slot: str, *, down: bool, enabled: bool) -> None:
        session = active_gml_layout()
        rect = ui.rect(slot)
        if session is None or rect is None:
            return
        x = session.window_position[0] + rect.x - imgui.get_scroll_x()
        y = session.window_position[1] + rect.y - imgui.get_scroll_y()
        center_x, center_y = x + rect.width / 2.0, y + rect.height / 2.0
        draw = imgui.get_window_draw_list()
        if down:
            points = ((center_x - 3.0, center_y - 2.0),
                      (center_x + 3.0, center_y - 2.0),
                      (center_x, center_y + 2.0))
        else:
            points = ((center_x - 3.0, center_y + 2.0),
                      (center_x + 3.0, center_y + 2.0),
                      (center_x, center_y - 2.0))
        color = GAMETHEME.colors.text_main if enabled else GAMETHEME.colors.text_dim
        draw.add_triangle_filled(*points, imgui.get_color_u32(color))

    def _render_capabilities(
        self,
        ui: GMLWidgets,
        listing: dict | None,
        designs: dict[str, dict],
        state,
    ) -> None:
        design = designs.get(str((listing or {}).get("design_id") or ""), {})
        values = self._saved_capabilities(design)
        parent = f"{_DESIGN_ROOT}/frmUnitSpecs/frmList"
        session = active_gml_layout()
        if session is None:
            return

        list_path = f"{parent}"
        list_component = session.layout.component(list_path)
        list_rect = session.rect_for(list_component) if list_component is not None else None
        if list_rect is None:
            return
        # The source scrollbar occupies the 14px slot immediately beside this frame.
        scroll_width = list_rect.width + 14.0
        session.resize_component(list_path, width=scroll_width)
        opened = imgui.begin_child(
            "unit_market.capabilities",
            (list_rect.width, list_rect.height),
            child_flags=imgui.ChildFlags_.borders,
            test_id="unit_market.capabilities",
            gml_id=list_path,
        )
        if opened:
            for key, label, component in DESIGN_METRICS:
                label_slot = f"{_CAPABILITIES_ROOT}/lbl{component}"
                meter_slot = f"{_CAPABILITIES_ROOT}/frm{component}"
                self._draw_scrolled_text(session, label_slot, label, f"unit_market.capability.{key}.label")
                self._draw_scrolled_capability(
                    session, meter_slot, key, values.get(key), state,
                )
        imgui.end_child()

    _saved_capabilities = staticmethod(saved_capabilities)

    @staticmethod
    def _draw_scrolled_text(session, slot: str, value: str, test_id: str) -> None:
        component = session.layout.component(slot)
        if component is None:
            return
        rect = session.rect_for(component)
        imgui.set_cursor_screen_pos((
            session.window_position[0] + rect.x - imgui.get_scroll_x(),
            session.window_position[1] + rect.y - imgui.get_scroll_y(),
        ))
        imgui.text_disabled(value, test_id=test_id)

    @staticmethod
    def _draw_scrolled_capability(
        session, slot: str, key: str, value: float | None, state,
    ) -> None:
        component = session.layout.component(slot)
        if component is None:
            return
        rect = session.rect_for(component)
        imgui.set_cursor_screen_pos((
            session.window_position[0] + rect.x - imgui.get_scroll_x(),
            session.window_position[1] + rect.y - imgui.get_scroll_y(),
        ))
        test_id = f"unit_market.capability.{key}"
        if value is None or key == "speed":
            reason = (
                "OpenPower stores speed and maneuverability separately; the source combines them."
                if key == "speed" else "This design has no saved OpenPower capability value."
            )
            imgui.progress_bar(
                0.0,
                (rect.width, rect.height),
                "N/A",
                test_id=test_id,
            )
            if imgui.is_item_hovered():
                imgui.set_tooltip(reason)
            return

        capability_bounds = contribution_for(state, ClientPresentationKeys.CAPABILITY_BOUNDS)
        capability_metadata = contribution_for(state, ClientPresentationKeys.CAPABILITY_METADATA)
        minimum, maximum = capability_bounds.get(key, (0.0, 0.0))
        fraction = 0.0 if maximum <= minimum else (value - minimum) / (maximum - minimum)
        fraction = min(1.0, max(0.0, fraction))
        display = f"{value:g}"
        unit = capability_metadata.get(key, {}).get("unit")
        imgui.progress_bar(
            fraction,
            (rect.width, rect.height),
            display,
            test_id=test_id,
        )
        if imgui.is_item_hovered():
            imgui.set_tooltip(f"OpenPower value: {display} {unit}" if unit else f"OpenPower value: {display}")

    @staticmethod
    def _format_money(value: float) -> str:
        return format_currency(value)
