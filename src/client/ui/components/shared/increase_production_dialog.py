from __future__ import annotations

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.instrumented_imgui import imgui
from src.shared.resource_production_policy import (
    PRODUCTION_INCREASE_PERCENTAGES,
    estimate_production_increase_cost,
    production_increase_basis,
)


class IncreaseProductionDialog:
    """Shows OpenPower production estimates in the source dialog layout."""

    _PERCENTAGES = PRODUCTION_INCREASE_PERCENTAGES

    def __init__(self) -> None:
        self._country_tag = ""
        self._resource_id = ""
        self._selected_percents: set[int] = set()
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def country_tag(self) -> str:
        return self._country_tag

    @property
    def resource_id(self) -> str:
        return self._resource_id

    def open(self, country_tag: str, resource_id: str) -> None:
        if not country_tag or not resource_id:
            return
        self._country_tag = str(country_tag).upper()
        self._resource_id = str(resource_id)
        self._selected_percents.clear()
        self._open = True

    def render(self, state, *, can_apply: bool) -> int | None:
        if not self._open:
            return None

        basis = production_increase_basis(state, self._country_tag, self._resource_id)
        selected_percent: int | None = None
        viewport = imgui.get_main_viewport()
        x = float(viewport.pos.x + (viewport.size.x - 340.0) / 2.0)
        y = float(viewport.pos.y + min(220.0, viewport.size.y - 164.0))
        with WindowManager.window(
            "Increase production",
            x=x,
            y=y,
            w=340,
            h=164,
            test_id="resources.increase_production.dialog",
            gml_template="Increase_Production_Window",
        ) as is_open:
            if not is_open:
                self._open = False
                return None

            for percent in self._PERCENTAGES:
                component = f"togIncrease{percent}"
                selected = percent in self._selected_percents
                imgui.push_style_color(
                    imgui.Col_.button,
                    (0.20, 0.35, 0.50, 1.0) if selected else (0.12, 0.14, 0.16, 1.0),
                )
                if imgui.button(
                    f"{percent}%##increase-{percent}",
                    test_id=f"resources.increase_production.percent.{percent}",
                    gml_id=f"Increase_Production_Window/frmInner/frmInner/{component}",
                ):
                    self._toggle_percent(percent)
                imgui.pop_style_color()

                amount_component = f"txtIncrease{percent}"
                cost = (
                    estimate_production_increase_cost(basis.annual_value_usd, percent)
                    if basis is not None
                    else None
                )
                cost_text = f"${cost:,.0f}" if cost is not None else "Unavailable"
                imgui.text(
                    cost_text,
                    test_id=f"resources.increase_production.cost.{percent}",
                    gml_id=f"Increase_Production_Window/frmInner/frmInner/{amount_component}",
                )
                if imgui.is_item_hovered():
                    imgui.set_tooltip(self._cost_tooltip(basis, cost))

            selected_percent = max(self._selected_percents, default=None)
            selected_cost = (
                estimate_production_increase_cost(basis.annual_value_usd, selected_percent)
                if basis is not None and selected_percent is not None
                else None
            )
            imgui.begin_disabled(not (can_apply and selected_cost is not None))
            apply_clicked = imgui.button(
                "✓",
                test_id="resources.increase_production.apply",
                gml_id="Increase_Production_Window/frmTitle/btnApply",
            )
            imgui.end_disabled()

            window_position = imgui.get_window_pos()
            imgui.set_cursor_screen_pos((float(window_position.x) + 37.0, float(window_position.y) + 147.0))
            imgui.text_disabled("OpenPower estimate: one year of added output.")

        if apply_clicked and selected_percent is not None and selected_cost is not None:
            self._open = False
            return selected_percent
        return None

    def _toggle_percent(self, percent: int) -> None:
        if percent in self._selected_percents:
            self._selected_percents.remove(percent)
        else:
            self._selected_percents.add(percent)

    @staticmethod
    def _cost_tooltip(basis, cost: float | None) -> str:
        if basis is None or cost is None:
            return "No positive production value is available for this resource."
        basis_label = "controlled regional output" if basis.source == "regional" else "national output"
        return (
            f"OpenPower estimate based on {basis_label}: one year of added production value. "
            f"Estimated investment: ${cost:,.2f}."
        )
