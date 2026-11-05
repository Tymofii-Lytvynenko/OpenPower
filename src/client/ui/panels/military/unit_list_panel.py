from __future__ import annotations

from dataclasses import dataclass

from modules.base.systems.military.capability_catalog import canonical_role
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.layouts.gml_layout import active_gml_layout
from src.client.ui.panels.military.presenter import MilitaryPresenter, UnitListRow
from src.client.ui.panels.military.unit_training_confirmation import (
    training_offer,
    training_unavailable_reason,
)
from src.client.ui.panels.military.unit_type_options import (
    DESIGN_UNIT_TYPE_OPTIONS,
    OPENPOWER_UNIT_TYPE_EXTENSIONS,
    REFERENCE_UNIT_TYPE_OPTIONS,
    source_unit_type_label,
)
from src.shared.actions import ActionDisbandUnits, ActionListUsedUnit


_GML_ROOT = "Unit_List_Window_New"
_GML_LIST = "frmInner/frmList"
_GML_ROWS = f"{_GML_LIST}/frmList"
_VISIBLE_ROWS = 20
_ROW_FRAME_HEIGHT = 16.0
_TRAINING_ORDER = {"Recruit": 0, "Regular": 1, "Veteran": 2, "Elite": 3}
_TRAINING_COLORS = {
    "Regular": (0.36, 0.66, 0.92, 1.0),
    "Veteran": (0.36, 0.78, 0.48, 1.0),
    "Elite": (0.94, 0.75, 0.28, 1.0),
}
_UNIT_TYPE_ROLE_BY_LABEL = {
    option.label: option.role for option in DESIGN_UNIT_TYPE_OPTIONS
}


@dataclass(frozen=True, slots=True)
class _UnitListEntry:
    unit_id: str
    unit_type: str
    quantity_text: str
    quantity_value: int | None
    name: str
    position: str
    status: str
    training_level: str
    for_sale: bool
    design_id: str = ""
    design_cost: float | None = None
    upkeep_value: float | None = None
    upkeep_text: str = "—"
    status_kind: str = "ready"
    tooltip: str = ""


class UnitListPanel:
    """Render REFERENCE's twenty-row unit roster and bind only available OpenPower actions."""

    def __init__(self, open_design_cb=None, open_train_cb=None):
        self._presenter = MilitaryPresenter()
        self._open_design_cb = open_design_cb
        self._open_train_cb = open_train_cb
        self._sort_key = "type"
        self._sort_ascending = True
        self._filter_type = "All"
        self._first_visible_row = 0
        self._selected_unit_ids: set[str] = set()
        self._training_submission_selection: frozenset[str] | None = None
        self._last_design_click: tuple[str, float] | None = None

    def render(self, state, context: PanelRenderContext) -> bool:
        viewport = imgui.get_io().display_size
        if viewport.x <= 0 or viewport.y <= 0:
            viewport = imgui.get_main_viewport().size
        x = max(0.0, (float(viewport.x) - 835.0) / 2.0)
        y = max(0.0, (float(viewport.y) - 427.0) / 2.0)
        with WindowManager.window(
            "UNIT LIST", x=x, y=y, w=835, h=427, test_id="unit_list.panel",
            fit_layout_width=True,
        ) as is_open:
            if not is_open:
                return False
            ui = GMLWidgets(_GML_ROOT)
            ui.frame(f"{_GML_LIST}")
            ui.frame(_GML_ROWS)
            self._render_content(state, context, ui)
            return True

    def _render_content(self, state, context: PanelRenderContext, ui: GMLWidgets) -> None:
        country_tag = str(context.target_tag or "").strip().upper()
        own_country = bool(context.is_own_country)
        entries = (
            self._own_entries(state, country_tag)
            if own_country
            else self._foreign_entries(state, country_tag)
        )
        self._render_type_filter(entries, ui)

        if not own_country:
            self._render_accuracy(state, country_tag, ui)

        self._render_headers(ui, own_country=own_country)
        entries = self._filtered_entries(entries)
        entries = self._sorted_entries(entries)
        max_first = max(0, len(entries) - _VISIBLE_ROWS)
        self._first_visible_row = min(max(0, self._first_visible_row), max_first)
        self._apply_wheel_scroll(ui, max_first)
        self._render_scrollbar(ui, max_first)
        self._render_rows(entries, own_country, ui)
        if own_country:
            self._render_actions(state, context, entries, country_tag, ui)

    def _own_entries(self, state, country_tag: str) -> list[_UnitListEntry]:
        return [self._entry_from_unit(row) for row in self._presenter.unit_rows(state, country_tag)]

    @staticmethod
    def _entry_from_unit(row: UnitListRow) -> _UnitListEntry:
        upkeep_value = row.upkeep
        return _UnitListEntry(
            unit_id=row.unit_id,
            unit_type=row.unit_type,
            quantity_text=_format_quantity(row.quantity),
            quantity_value=row.quantity,
            name=row.design_name or "Unknown design",
            position=row.location or "Unknown location",
            status=row.status,
            training_level=row.training_level or "Recruit",
            for_sale=row.for_sale,
            design_id=row.design_id,
            design_cost=row.design_cost,
            upkeep_value=upkeep_value,
            upkeep_text=("—" if upkeep_value is None else _format_quantity(round(upkeep_value))),
            status_kind=_status_kind(row.status),
            tooltip=(
                f"Unit: {row.unit_id}"
                + f" · Training: {row.training_level or 'Recruit'}"
                + (" · Listed for sale" if row.for_sale else "")
                + (f" · Route: {row.route_summary}" if row.route_summary else "")
                + (" · Annual OpenPower budget estimate, not the REFERENCE formula; includes base military expense, readiness and design maintenance."
                   if upkeep_value is not None else "")
            ),
        )

    def _foreign_entries(self, state, country_tag: str) -> list[_UnitListEntry]:
        estimates = self._presenter.foreign_force_estimates_for_country(state, country_tag)
        entries = self._estimate_entries(estimates, country_tag)
        signals = self._presenter.mobilization_signals_for_country(state, country_tag)
        entries.extend(self._signal_entries(signals, country_tag))
        return entries

    @staticmethod
    def _estimate_entries(estimates, country_tag: str) -> list[_UnitListEntry]:
        entries: list[_UnitListEntry] = []
        for estimate_index, estimate in enumerate(estimates):
            source = str(estimate.get("source_country_id") or "").strip().upper()
            source_type = str(estimate.get("source_type") or "none").strip().lower()
            observed_at = max(0, int(estimate.get("observed_at_minute") or 0))
            observed = f"t={observed_at}"
            target = str(estimate.get("target_country_name") or estimate.get("target_country_id") or country_tag)
            estimate_status = str(estimate.get("status") or "unknown").strip().lower()
            status = "Outdated" if estimate_status == "outdated" else (
                "Unknown" if estimate_status == "unknown" else "Estimate"
            )
            count_range = estimate.get("total_count_range")
            quantity = (
                f"{int(count_range[0]):,}–{int(count_range[1]):,}".replace(",", " ")
                if count_range is not None else "Unknown"
            )
            source_context = _format_intelligence_context(
                source,
                source_type,
                observed_at,
                estimate.get("confidence"),
                estimate.get("freshness"),
                estimate.get("source_factors"),
            )
            estimate_summary = _foreign_estimate_summary(status, quantity)
            entries.append(_UnitListEntry(
                unit_id="",
                unit_type="Estimated forces",
                quantity_text=quantity,
                quantity_value=None,
                name=target,
                position=_source_position(source, observed),
                status=status,
                training_level="",
                for_sale=False,
                status_kind="warning" if status == "Outdated" else "info",
                tooltip=(
                    f"{estimate_summary}\nAggregate estimate only; no individual units are shown.\n"
                    f"{source_context}"
                ),
            ))
            for role, minimum, maximum in estimate.get("role_count_ranges") or ():
                role_range = f"{int(minimum):,}–{int(maximum):,}".replace(",", " ")
                entries.append(_UnitListEntry(
                    unit_id="",
                    unit_type=str(role).replace("_", " ").title(),
                    quantity_text=role_range,
                    quantity_value=None,
                    name=f"{target} · estimate {estimate_index + 1}",
                    position=_source_position(source, observed),
                    status=status,
                    training_level="",
                    for_sale=False,
                    status_kind="warning" if status == "Outdated" else "info",
                    tooltip=(
                        f"Estimated {role.replace('_', ' ')} range: {role_range}.\n"
                        f"No individual units are shown.\n{source_context}"
                    ),
                ))

        return entries

    @staticmethod
    def _signal_entries(signals, country_tag: str) -> list[_UnitListEntry]:
        entries: list[_UnitListEntry] = []
        for signal in signals:
            target = str(signal.get("target_country_name") or signal.get("target_country_id") or country_tag)
            source = str(signal.get("source_country_id") or "").strip().upper()
            source_type = str(signal.get("source_type") or "none").strip().lower()
            observed_at = max(0, int(signal.get("observed_at_minute") or 0))
            signal_status = "Outdated signal" if signal.get("status") == "outdated" else (
                f"{signal.get('from_readiness', '?')} → {signal.get('to_readiness', '?')}"
            )
            source_context = _format_intelligence_context(
                source,
                source_type,
                observed_at,
                signal.get("confidence"),
                signal.get("freshness"),
                signal.get("source_factors"),
            )
            entries.append(_UnitListEntry(
                unit_id="",
                unit_type=f"{str(signal.get('domain') or 'military').title()} signal",
                quantity_text="—",
                quantity_value=None,
                name=target,
                position=_source_position(source, f"t={observed_at}"),
                status=signal_status,
                training_level="",
                for_sale=False,
                status_kind="warning" if signal.get("status") == "outdated" else "info",
                tooltip=(
                    f"Aggregate readiness signal: {signal.get('from_readiness', '?')} → "
                    f"{signal.get('to_readiness', '?')}.\nNo unit identity is shown.\n{source_context}"
                ),
            ))
        return entries

    def _render_type_filter(self, entries: list[_UnitListEntry], ui: GMLWidgets) -> None:
        label_slot = f"{_GML_LIST}/lblUnitType"
        combo_slot = f"{_GML_LIST}/cboUnitType"
        ui.text(label_slot, "UNIT TYPE", test_id="unit_list.filter.label")
        entry_roles = {canonical_role(entry.unit_type) for entry in entries}
        native_roles = {option.role for option in REFERENCE_UNIT_TYPE_OPTIONS}
        extensions = [
            option for option in OPENPOWER_UNIT_TYPE_EXTENSIONS
            if option.role in entry_roles
        ]
        extension_roles = {option.role for option in extensions}
        extra_types = sorted(
            {
                entry.unit_type for entry in entries
                if canonical_role(entry.unit_type) not in native_roles | extension_roles
            },
            key=str.casefold,
        )
        options = [
            "All",
            *(option.label for option in REFERENCE_UNIT_TYPE_OPTIONS),
            *(option.label for option in extensions),
            *extra_types,
        ]
        if self._filter_type not in options:
            self._filter_type = "All"
        selected_index = options.index(self._filter_type)
        imgui.push_style_var(imgui.StyleVar_.frame_padding, (3.0, 2.0))
        try:
            changed, new_index = imgui.combo(
                "##unit-list-filter",
                selected_index,
                options,
                test_id="unit_list.filter",
                gml_id=ui.path(combo_slot),
            )
        finally:
            imgui.pop_style_var()
        if changed and 0 <= int(new_index) < len(options):
            self._filter_type = options[int(new_index)]
            self._first_visible_row = 0
            self._selected_unit_ids.clear()

    def _render_accuracy(self, state, country_tag: str, ui: GMLWidgets) -> None:
        estimates = self._presenter.foreign_force_estimates_for_country(state, country_tag)
        confidence_values = [
            max(0.0, min(1.0, float(row.get("confidence") or 0.0)))
            for row in estimates
        ]
        confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
        ui.text(f"{_GML_LIST}/lblAccuracy", "ESTIMATE CONFIDENCE", test_id="unit_list.estimate.label")
        ui.text(
            f"{_GML_LIST}/txtValue",
            f"{confidence:.0%}" if confidence_values else "—",
            right=True,
            test_id="unit_list.estimate.confidence",
            tooltip="Confidence belongs to aggregate OpenPower intelligence estimates.",
        )
        ui.meter(
            f"{_GML_LIST}/frmAccuracy",
            confidence,
            GAMETHEME.colors.info if confidence_values else GAMETHEME.colors.text_dim,
        )

    def _render_headers(self, ui: GMLWidgets, *, own_country: bool) -> None:
        headers = (
            ("type", "Type", "btnType", "btnTypeIcon"),
            ("quantity", "Qty", "btnQty", "btnQtyIcon"),
            ("name", "Name", "btnName", "btnNameIcon"),
            ("position", "Position", "btnPosition", ""),
            ("status", "Status", "btnStatus", "btnStatusIcon"),
            ("upkeep", "Upkeep", "btnUpkeep", "btnUpkeepIcon"),
            ("value", "Value", "btnValue", "btnValueIcon"),
        )
        for sort_key, label, slot, icon_slot in headers:
            enabled = sort_key != "upkeep" or own_country
            tooltip = f"Sort by OpenPower annual upkeep estimate" if sort_key == "upkeep" and own_country else (
                "Per-unit upkeep is hidden for foreign forces."
                if sort_key == "upkeep" else f"Sort by {label.lower()}"
            )
            header_path = f"{_GML_LIST}/{slot}"
            icon_path = f"{_GML_LIST}/{icon_slot}" if icon_slot else ""
            header_rect = ui.rect(header_path)
            icon_rect = ui.rect(icon_path) if icon_path else None
            hit_width = None
            if (header_rect and icon_rect
                    and header_rect.x < icon_rect.x < header_rect.x + header_rect.width):
                # The source sort arrow is its own click target; stop the label
                # hitbox at the arrow slot so one click cannot trigger both.
                hit_width = icon_rect.x - header_rect.x
            if enabled and ui.hitbox(
                header_path,
                f"unit_list.sort.{sort_key}",
                tooltip=tooltip,
                width=hit_width,
            ):
                self._select_sort(sort_key)
            elif not enabled:
                ui.hitbox(
                    header_path,
                    f"unit_list.sort.{sort_key}",
                    enabled=False,
                    tooltip=tooltip,
                    width=hit_width,
                )
            self._draw_header_text(ui, f"{_GML_LIST}/{slot}", label, enabled)
            if icon_slot:
                if enabled and ui.hitbox(
                    icon_path,
                    f"unit_list.sort.{sort_key}.arrow",
                    tooltip=tooltip,
                ):
                    self._select_sort(sort_key)
                elif not enabled:
                    ui.hitbox(
                        icon_path,
                        f"unit_list.sort.{sort_key}.arrow",
                        enabled=False,
                        tooltip=tooltip,
                    )
                self._draw_sort_icon(ui, f"{_GML_LIST}/{icon_slot}", sort_key, enabled=enabled)

        if ui.hitbox(
            f"{_GML_LIST}/btnTrainingIcon",
            "unit_list.sort.training",
            tooltip="Sort by training level",
        ):
            self._select_sort("training")
        self._draw_header_text(ui, f"{_GML_LIST}/btnTrainingIcon", "T", True)

        if ui.hitbox(
            f"{_GML_LIST}/btnForSaleIcon",
            "unit_list.sort.for_sale",
            tooltip="Sort by sale status",
        ):
            self._select_sort("for_sale")
        self._draw_header_text(ui, f"{_GML_LIST}/btnForSaleIcon", "$", True)

    @staticmethod
    def _draw_header_text(ui: GMLWidgets, slot: str, label: str, enabled: bool) -> None:
        rect = ui.rect(slot)
        if rect is None:
            return
        color = GAMETHEME.colors.text_main if enabled else GAMETHEME.colors.text_dim
        ui.text_at(
            slot,
            label,
            offset=(3.0, 0.0),
            max_width=max(1.0, rect.width - 5.0),
            color=color,
            tooltip=(None if enabled else "OpenPower does not expose this source value."),
        )

    def _draw_sort_icon(self, ui: GMLWidgets, slot: str, sort_key: str, *, enabled: bool = True) -> None:
        if sort_key != self._sort_key:
            return
        self._draw_header_text(ui, slot, "▲" if self._sort_ascending else "▼", enabled)

    def _select_sort(self, sort_key: str) -> None:
        if self._sort_key == sort_key:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_key = sort_key
            self._sort_ascending = True
        self._first_visible_row = 0

    def _filtered_entries(self, entries: list[_UnitListEntry]) -> list[_UnitListEntry]:
        if self._filter_type == "All":
            return entries
        selected_role = _UNIT_TYPE_ROLE_BY_LABEL.get(self._filter_type)
        if selected_role is not None:
            return [
                entry for entry in entries
                if canonical_role(entry.unit_type) == selected_role
            ]
        return [entry for entry in entries if entry.unit_type == self._filter_type]

    def _sorted_entries(self, entries: list[_UnitListEntry]) -> list[_UnitListEntry]:
        key_functions = {
            "type": lambda entry: entry.unit_type.casefold(),
            "quantity": lambda entry: entry.quantity_value,
            "training": lambda entry: _TRAINING_ORDER.get(entry.training_level, None),
            "name": lambda entry: entry.name.casefold() if entry.name else None,
            "status": lambda entry: entry.status.casefold() if entry.status else None,
            "value": lambda entry: entry.design_cost,
            "upkeep": lambda entry: entry.upkeep_value,
            "for_sale": lambda entry: entry.for_sale,
        }
        key_function = key_functions.get(self._sort_key, key_functions["type"])
        known = [entry for entry in entries if key_function(entry) is not None]
        unknown = [entry for entry in entries if key_function(entry) is None]
        known.sort(key=key_function, reverse=not self._sort_ascending)
        return [*known, *unknown]

    def _apply_wheel_scroll(self, ui: GMLWidgets, max_first: int) -> None:
        if max_first <= 0:
            self._first_visible_row = 0
            return
        session = active_gml_layout()
        rect = ui.rect(_GML_ROWS)
        if session is None or rect is None:
            return
        mouse = imgui.get_io().mouse_pos
        left = session.window_position[0] + rect.x
        top = session.window_position[1] + rect.y
        if left <= mouse.x <= left + rect.width and top <= mouse.y <= top + rect.height:
            wheel = float(imgui.get_io().mouse_wheel)
            if wheel:
                step = max(1, round(abs(wheel) * 3.0))
                self._first_visible_row = max(
                    0,
                    min(max_first, self._first_visible_row - (step if wheel > 0 else -step)),
                )

    def _render_scrollbar(self, ui: GMLWidgets, max_first: int) -> None:
        slot = f"{_GML_LIST}/scrList"
        rect = ui.rect(slot)
        session = active_gml_layout()
        if rect is None or session is None:
            return

        clicked = ui.hitbox(
            slot,
            "unit_list.scrollbar",
            enabled=max_first > 0,
            tooltip="Scroll the unit roster",
        )
        thumb_height = max(18.0, rect.height * _VISIBLE_ROWS / (_VISIBLE_ROWS + max_first))
        travel = max(0.0, rect.height - thumb_height)
        if max_first > 0 and (clicked or imgui.is_item_active()):
            local_y = float(imgui.get_io().mouse_pos.y) - session.window_position[1] - rect.y
            ratio = max(0.0, min(1.0, (local_y - thumb_height / 2.0) / max(1.0, travel)))
            self._first_visible_row = round(ratio * max_first)

        track_x = session.window_position[0] + rect.x
        track_y = session.window_position[1] + rect.y
        draw = imgui.get_window_draw_list()
        draw.add_rect_filled(
            (track_x, track_y), (track_x + rect.width, track_y + rect.height),
            imgui.get_color_u32(GAMETHEME.colors.bg_input),
        )
        thumb_y = track_y + travel * (self._first_visible_row / max_first if max_first else 0.0)
        draw.add_rect_filled(
            (track_x + 2.0, thumb_y),
            (track_x + rect.width - 2.0, thumb_y + thumb_height),
            imgui.get_color_u32(GAMETHEME.colors.text_dim),
        )

    def _render_rows(self, entries: list[_UnitListEntry], own_country: bool,
                     ui: GMLWidgets) -> None:
        visible_entries = entries[self._first_visible_row:self._first_visible_row + _VISIBLE_ROWS]
        if not visible_entries:
            message = (
                "No units match this filter."
                if own_country and entries == [] and self._filter_type != "All"
                else "No deployed units are tracked for this country."
                if own_country
                else "No authorized aggregate force estimate is available."
            )
            ui.text_at(
                f"{_GML_ROWS}/frm1",
                message,
                offset=(6.0, 0.0),
                max_width=720.0,
                color=GAMETHEME.colors.text_dim,
                test_id="unit_list.empty",
            )
            return

        for row_index in range(_VISIBLE_ROWS):
            frame_slot = f"{_GML_ROWS}/frm{row_index + 1}"
            entry_index = self._first_visible_row + row_index
            if entry_index >= len(entries):
                continue
            entry = entries[entry_index]
            selected = own_country and entry.unit_id in self._selected_unit_ids
            if own_country and entry.unit_id:
                frame_rect = ui.rect(frame_slot)
                next_rect = (
                    ui.rect(f"{_GML_ROWS}/frm{row_index + 2}")
                    if row_index + 1 < _VISIBLE_ROWS else None
                )
                hit_height = None
                if (frame_rect and next_rect
                        and frame_rect.y < next_rect.y < frame_rect.y + frame_rect.height - 1.0):
                    # A few scaled source rows compress by two pixels; stop the
                    # selection target at the next row to keep clicks exclusive.
                    hit_height = next_rect.y - frame_rect.y
                test_id = (
                    f"unit_list.view_design.{entry.unit_id}"
                    if entry.design_id else f"unit_list.row.{entry.unit_id}"
                )
                clicked = ui.hitbox(
                    frame_slot,
                    test_id,
                    tooltip=entry.tooltip,
                    height=hit_height,
                )
                if clicked:
                    self._training_submission_selection = None
                    now = float(imgui.get_time())
                    previous_click = self._last_design_click
                    double_click_window = float(
                        getattr(imgui.get_io(), "mouse_double_click_time", 0.3)
                    )
                    is_double_click = (
                        previous_click is not None
                        and previous_click[0] == entry.unit_id
                        and 0.0 <= now - previous_click[1] <= double_click_window
                    )
                    self._last_design_click = (entry.unit_id, now)
                    if imgui.get_io().key_ctrl:
                        if entry.unit_id in self._selected_unit_ids:
                            self._selected_unit_ids.remove(entry.unit_id)
                        else:
                            self._selected_unit_ids.add(entry.unit_id)
                    else:
                        self._selected_unit_ids = {entry.unit_id}
                    selected = entry.unit_id in self._selected_unit_ids
                    if (
                        (imgui.is_mouse_double_clicked(imgui.MouseButton_.left) or is_double_click)
                        and entry.design_id
                        and self._open_design_cb is not None
                    ):
                        self._open_design_cb(entry.design_id)

            if selected:
                self._draw_row_selection(ui, frame_slot)
            self._render_entry(entry, row_index + 1, selected, ui)

    @staticmethod
    def _draw_row_selection(ui: GMLWidgets, slot: str) -> None:
        rect = ui.rect(slot)
        session = active_gml_layout()
        if rect is None or session is None:
            return
        x = session.window_position[0] + rect.x - imgui.get_scroll_x()
        y = session.window_position[1] + rect.y - imgui.get_scroll_y()
        imgui.get_window_draw_list().add_rect_filled(
            (x, y),
            (x + rect.width, y + rect.height),
            imgui.get_color_u32((0.25, 0.27, 0.3, 0.72)),
        )

    def _render_entry(self, entry: _UnitListEntry, row_number: int, selected: bool,
                      ui: GMLWidgets) -> None:
        row_slot = f"{_GML_ROWS}/frm{row_number}"
        color = GAMETHEME.colors.text_main
        ui.text(
            f"{row_slot}/txtType", source_unit_type_label(entry.unit_type),
            color=color, tooltip=entry.tooltip,
            test_id=f"unit_list.row.type.{entry.unit_id or row_number}",
        )
        ui.text(
            f"{row_slot}/txtQty", entry.quantity_text,
            right=True, tooltip=entry.tooltip,
            test_id=f"unit_list.row.quantity.{entry.unit_id or row_number}",
        )
        ui.text(
            f"{row_slot}/txtName", entry.name,
            tooltip=entry.tooltip,
            test_id=f"unit_list.row.name.{entry.unit_id or row_number}",
        )
        ui.text(
            f"{row_slot}/txtPosition", entry.position,
            tooltip=entry.tooltip,
            test_id=f"unit_list.row.position.{entry.unit_id or row_number}",
        )
        ui.text(
            f"{row_slot}/txtStatus", entry.status,
            color=_status_color(entry.status_kind), tooltip=entry.tooltip,
            test_id=f"unit_list.row.status.{entry.unit_id or row_number}",
        )
        ui.text(
            f"{row_slot}/txtUpkeep", entry.upkeep_text,
            right=True,
            tooltip=(entry.tooltip if entry.upkeep_value is not None else "Per-unit upkeep is unavailable for this row."),
            test_id=f"unit_list.row.upkeep.{entry.unit_id or row_number}",
        )
        value = "—" if entry.design_cost is None else _format_quantity(round(entry.design_cost))
        ui.text(
            f"{row_slot}/txtValue", value,
            right=True,
            tooltip=("OpenPower does not have an authoritative design value." if entry.design_cost is None
                     else "Unit design cost"),
            test_id=f"unit_list.row.value.{entry.unit_id or row_number}",
        )
        self._draw_row_marker(ui, f"{row_slot}/picTraining", _TRAINING_COLORS.get(entry.training_level))
        if entry.for_sale:
            self._draw_row_marker(ui, f"{row_slot}/picSell", GAMETHEME.colors.warning)

    @staticmethod
    def _draw_row_marker(ui: GMLWidgets, slot: str, color) -> None:
        if color is None:
            return
        rect = ui.rect(slot)
        session = active_gml_layout()
        if rect is None or session is None:
            return
        x = session.window_position[0] + rect.x
        y = session.window_position[1] + rect.y
        imgui.get_window_draw_list().add_rect_filled(
            (x + 1.0, y + 2.0),
            (x + max(2.0, rect.width - 1.0), y + rect.height - 2.0),
            imgui.get_color_u32(color),
        )

    def _render_actions(self, state, context: PanelRenderContext,
                        entries: list[_UnitListEntry], country_tag: str,
                        ui: GMLWidgets) -> None:
        visible_ids = {entry.unit_id for entry in entries if entry.unit_id}
        selected_ids = sorted(self._selected_unit_ids & visible_ids)
        selected_entries = [entry for entry in entries if entry.unit_id in selected_ids]
        client = context.net_client
        training_already_submitted = (
            self._training_submission_selection == frozenset(selected_ids)
        )

        marketable_ids = {
            str(row.get("id") or "")
            for row in self._presenter.marketable_units_for_country(state, country_tag)
        }
        can_sell = (
            bool(selected_ids)
            and client is not None
            and not training_already_submitted
            and all(entry.design_id and entry.unit_id in marketable_ids for entry in selected_entries)
        )
        sell_tooltip = (
            "Wait for updated unit data or change the selection before submitting another action."
            if training_already_submitted else
            "Selected units will be listed at 75% of design cost."
            if can_sell else
            "Select available, non-infantry units that are not moving, training, engaged, or already listed."
        )
        if ui.button(
            f"{_GML_LIST}/btnSell", "SELL", "unit_list.sell",
            enabled=can_sell, dynamic_enabled=True, tooltip=sell_tooltip,
        ):
            for unit_id in selected_ids:
                client.send_action(ActionListUsedUnit(client.player_id, country_tag, unit_id))
            self._selected_unit_ids.clear()

        quotes = {
            unit_id: training_offer(state, unit_id, country_tag)
            for unit_id in selected_ids
        }
        can_train = (
            bool(selected_ids)
            and not training_already_submitted
            and client is not None
            and self._open_train_cb is not None
            and all(quote is not None for quote in quotes.values())
        )
        if training_already_submitted:
            train_tooltip = "Wait for updated unit data or change the selection before submitting TRAIN again."
        elif can_train:
            train_tooltip = f"Open a confirmation for {len(selected_ids)} selected unit(s)."
        elif not selected_ids:
            train_tooltip = "Select one or more units first."
        elif client is None or self._open_train_cb is None:
            train_tooltip = "Training confirmation is unavailable."
        else:
            unavailable_id = next(unit_id for unit_id, quote in quotes.items() if quote is None)
            train_tooltip = training_unavailable_reason(state, unavailable_id, country_tag)
        if ui.button(
            f"{_GML_LIST}/btnTrain", "TRAIN", "unit_list.train",
            enabled=can_train, dynamic_enabled=True, tooltip=train_tooltip,
        ):
            # Keep the selection while the confirmation is open so Cancel can return to it.
            selected_submission = frozenset(selected_ids)

            def mark_submitted() -> None:
                self._training_submission_selection = selected_submission

            self._open_train_cb(
                state,
                selected_ids,
                on_accept=mark_submitted,
            )

        can_disband = bool(selected_ids) and client is not None
        disband_tooltip = (
            f"Disband {len(selected_ids)} selected unit(s)."
            if can_disband else "Select one or more owned units first."
        )
        if ui.button(
            f"{_GML_LIST}/btnDisband", "DISBAND", "unit_list.disband",
            enabled=can_disband, dynamic_enabled=True, tooltip=disband_tooltip,
        ):
            client.send_action(ActionDisbandUnits(client.player_id, selected_ids))
            self._selected_unit_ids.clear()


def _format_quantity(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


def _foreign_estimate_summary(status: str, quantity: str) -> str:
    if status == "Outdated":
        return "Outdated intelligence; current force size unknown."
    if status == "Unknown":
        return "Force strength unknown; no current observation is available."
    return f"Estimated force strength: {quantity} units."


def _source_position(source: str, observed: str) -> str:
    if not source:
        return f"No source · {observed}"
    return f"{source} · {observed}"


def _format_intelligence_context(
    source: str,
    source_type: str,
    observed_at: int,
    confidence,
    freshness,
    source_factors,
) -> str:
    if source:
        source_label = f"Source {source}"
        if source_type not in {"", "none"}:
            source_label += f" ({source_type})"
        details = [f"{source_label} · observed at game minute {observed_at}"]
    else:
        details = ["No intelligence source is available"]
    details.append(
        f"Confidence {_format_percentage(confidence)} · freshness {_format_percentage(freshness)}"
    )
    if isinstance(source_factors, dict):
        for key, label in (
            ("observer_telecom", "Observer telecom"),
            ("target_telecom", "Target telecom"),
        ):
            if key in source_factors:
                details.append(f"{label} {_format_percentage(source_factors[key])}")
        coverage = str(source_factors.get("intelligence_coverage") or "").strip().lower()
        if coverage in {"none", "limited", "sustained", "dense"}:
            details.append(f"Intelligence coverage {coverage}")
    return "\n".join(details) + "."


def _format_percentage(value) -> str:
    try:
        fraction = float(value or 0.0)
    except (TypeError, ValueError):
        fraction = 0.0
    fraction = max(0.0, min(1.0, fraction))
    return f"{fraction:.0%}"


def _status_kind(status: str) -> str:
    normalized = str(status or "").casefold()
    if "block" in normalized or "outdated" in normalized:
        return "warning"
    if "move" in normalized or "transit" in normalized or "train" in normalized:
        return "info"
    if "ready" in normalized or "fortified" in normalized or "parked" in normalized:
        return "success"
    return "muted"


def _status_color(kind: str):
    return {
        "warning": GAMETHEME.colors.warning,
        "info": GAMETHEME.colors.info,
        "success": GAMETHEME.colors.positive,
        "muted": GAMETHEME.colors.text_dim,
    }.get(kind, GAMETHEME.colors.text_main)
