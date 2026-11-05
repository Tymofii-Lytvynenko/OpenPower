from __future__ import annotations

import numpy as np

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.instrumented_implot import implot
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.ui_anchor_registry import UIAnchorRegistry
from src.client.ui.layouts.gml_layout import active_gml_layout
from src.client.ui.panels.politics.relations_presenter import RelationsPresenter


class RelationsPanel:
    """Read-only country pair selector and relation history graph."""

    def __init__(self, presenter: RelationsPresenter | None = None) -> None:
        self._presenter = presenter or RelationsPresenter()
        self._country_a = ""
        self._country_b = ""

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window(
            "RELATIONS",
            x=300,
            y=130,
            w=317,
            h=170,
            test_id="relations.panel",
            gml_template="Relations_Window",
        ) as is_open:
            if not is_open:
                return False
            if UIAnchorRegistry.is_target("relations.panel.close"):
                # The native title-bar close button is not exposed as an instrumented ImGui item.
                position = imgui.get_window_pos()
                size = imgui.get_window_size()
                title_height = imgui.get_frame_height()
                UIAnchorRegistry.record(
                    "relations.panel.close",
                    float(position.x + size.x - title_height),
                    float(position.y),
                    float(title_height),
                    float(title_height),
                )
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        countries = self._presenter.countries(state)
        if len(countries) < 2:
            imgui.text_disabled("At least two country records are required to compare relations.")
            return

        by_tag = {country.tag: index for index, country in enumerate(countries)}
        if self._country_a not in by_tag:
            self._country_a = str(context.target_tag or "").strip().upper()
            if self._country_a not in by_tag:
                self._country_a = countries[0].tag
        if self._country_b not in by_tag or self._country_b == self._country_a:
            self._country_b = next(country.tag for country in countries if country.tag != self._country_a)

        labels = [country.label for country in countries]
        changed_a, index_a = self._country_selector(
            "Country A",
            by_tag[self._country_a],
            labels,
            label_component="lblCountryA",
            combo_component="cboCountryA",
            test_id="relations.country_a",
        )
        changed_b, index_b = self._country_selector(
            "Country B",
            by_tag[self._country_b],
            labels,
            label_component="lblCountryB",
            combo_component="cboCountryB",
            test_id="relations.country_b",
        )
        if changed_a:
            self._country_a = countries[index_a].tag
        if changed_b:
            self._country_b = countries[index_b].tag

        if self._country_a == self._country_b:
            imgui.text_disabled("Choose two different countries.")
            return

        pair = self._presenter.build_pair(state, self._country_a, self._country_b)
        if pair is None:
            imgui.text_disabled("Relation data is unavailable for this pair.")
            return

        if pair.current_value is None:
            relation_summary = f"{pair.country_a.name} → {pair.country_b.name}: unavailable"
        else:
            relation_summary = (
                f"{pair.country_a.name} → {pair.country_b.name}: "
                f"{pair.current_value:+.1f} relation points"
            )
        imgui.text(
            f"{pair.country_a.tag} → {pair.country_b.tag}: "
            + ("unavailable" if pair.current_value is None else f"{pair.current_value:+.1f}"),
            gml_id="Relations_Window/frmInner/frmRelations/lblTitle",
            test_id="relations.summary",
        )
        if imgui.is_item_hovered():
            imgui.set_tooltip(relation_summary)

        graph_rect = self._graph_rect()
        if not pair.history:
            # UIGraph is a custom canvas, so a text widget bound to its GML ID falls back to flow.
            GMLWidgets("Relations_Window/frmInner/frmRelations").text_at(
                "UIGraph",
                "No relation history recorded.",
                offset=(6.0, 4.0),
                max_width=graph_rect.width - 12.0 if graph_rect is not None else 240.0,
                color=(0.62, 0.65, 0.68, 1.0),
                test_id="relations.no_history",
            )
            return

        x_values = np.asarray([minute / 1440.0 for minute, _ in pair.history], dtype=np.float64)
        y_values = np.asarray([value for _, value in pair.history], dtype=np.float64)
        if graph_rect is None:
            graph_size = imgui.ImVec2(-1.0, 39.0)
        else:
            graph_size = imgui.ImVec2(graph_rect.width, graph_rect.height)
            window_position = imgui.get_window_pos()
            imgui.set_cursor_screen_pos((
                window_position.x + graph_rect.x,
                window_position.y + graph_rect.y,
            ))
        if implot.begin_plot(
            "Relation history##RelationsPanel",
            graph_size,
            implot.Flags_.canvas_only,
        ):
            try:
                implot.setup_axes(
                    "",
                    "",
                    implot.AxisFlags_.no_decorations,
                    implot.AxisFlags_.no_decorations,
                )
                implot.setup_axis_limits(implot.ImAxis_.y1, -100.0, 100.0)
                implot.plot_line("Relations", x_values, y_values)
            finally:
                implot.end_plot()

    def _country_selector(
        self,
        label: str,
        selected_index: int,
        options: list[str],
        *,
        label_component: str,
        combo_component: str,
        test_id: str,
    ) -> tuple[bool, int]:
        imgui.text(label, gml_id=self._component_path(label_component))
        imgui.push_style_var(imgui.StyleVar_.frame_padding, (4.0, 0.5))
        try:
            return imgui.combo(
                f"##{label.replace(' ', '')}",
                selected_index,
                options,
                test_id=test_id,
                gml_id=self._component_path(combo_component),
            )
        finally:
            imgui.pop_style_var()

    @staticmethod
    def _component_path(component_id: str) -> str:
        return f"Relations_Window/frmInner/frmRelations/{component_id}"

    @staticmethod
    def _graph_rect():
        layout = active_gml_layout()
        component = layout.layout.component("UIGraph") if layout is not None else None
        return layout.rect_for(component) if layout is not None and component is not None else None
