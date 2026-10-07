from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.ui.panels.shared.panel_widgets import draw_empty_state


class UnitListPanel:
    def __init__(self):
        self._presenter = MilitaryPresenter()

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("UNIT LIST", x=520, y=100, w=760, h=420) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        rows = self._presenter.unit_rows(
            state,
            context.target_tag,
            context.presentation_total_minutes,
        )
        if not rows:
            draw_empty_state("No deployed units are tracked for the selected country.")
            self._render_foreign_estimates(state, context.target_tag)
            return

        flags = imgui.TableFlags_.borders | imgui.TableFlags_.row_bg | imgui.TableFlags_.scroll_y | imgui.TableFlags_.sizing_stretch_prop
        if not imgui.begin_table("unit_list_table", 7, flags, (0.0, 0.0)):
            return

        imgui.table_setup_column("UNIT")
        imgui.table_setup_column("TYPE", imgui.TableColumnFlags_.width_fixed, 130.0)
        imgui.table_setup_column("STRENGTH", imgui.TableColumnFlags_.width_fixed, 90.0)
        imgui.table_setup_column("LOCATION")
        imgui.table_setup_column("STATUS", imgui.TableColumnFlags_.width_fixed, 90.0)
        imgui.table_setup_column("PROGRESS", imgui.TableColumnFlags_.width_fixed, 80.0)
        imgui.table_setup_column("ROUTE / ORDER")
        imgui.table_headers_row()

        for row in rows:
            imgui.table_next_row()
            imgui.table_next_column()
            imgui.text(row.unit_id)
            imgui.table_next_column()
            imgui.text(row.unit_type)
            imgui.table_next_column()
            imgui.text(f"{row.strength:,}".replace(",", " "))
            imgui.table_next_column()
            imgui.text(row.location)
            imgui.table_next_column()
            status_color = GAMETHEME.colors.info if row.status in {"Moving", "Parked"} else GAMETHEME.colors.text_main
            imgui.text_colored(status_color, row.status)
            imgui.table_next_column()
            imgui.text(f"{row.progress_pct:.0f}%")
            imgui.table_next_column()
            if row.route_summary:
                imgui.text_wrapped(row.route_summary)
            else:
                imgui.text_disabled("—")

        imgui.end_table()
        self._render_foreign_estimates(state, context.target_tag)

    def _render_foreign_estimates(self, state, country_tag: str) -> None:
        estimates = self._presenter.foreign_force_estimates_for_country(state, country_tag)
        signals = self._presenter.mobilization_signals_for_country(state, country_tag)
        if not estimates and not signals:
            return
        if estimates:
            imgui.separator()
            imgui.text("FOREIGN FORCE ESTIMATES")
            for estimate in estimates:
                target = estimate["target_country_name"] or estimate["target_country_id"]
                source = estimate["source_country_id"] or "Unknown source"
                observed = f"t={estimate['observed_at_minute']}"
                if estimate["status"] == "outdated":
                    imgui.text(f"{target}: outdated intelligence; current force size unknown")
                elif estimate["status"] == "unknown":
                    imgui.text(f"{target}: force strength unknown (no authorized current observation)")
                elif estimate["total_count_range"] is None:
                    imgui.text(f"{target}: force composition unknown")
                else:
                    low, high = estimate["total_count_range"]
                    imgui.text(f"{target}: estimated {low}–{high} units")
                    if estimate["role_count_ranges"]:
                        role_text = " · ".join(
                            f"{role.replace('_', ' ').title()} {minimum}–{maximum}"
                            for role, minimum, maximum in estimate["role_count_ranges"]
                        )
                        imgui.text_wrapped(role_text)
                if estimate["source_type"] == "none" and estimate["status"] == "unknown":
                    imgui.text_disabled("No authorized source · confidence unavailable · current force unknown")
                else:
                    imgui.text_disabled(
                        f"Source {source} ({estimate['source_type']}) · "
                        f"confidence {estimate['confidence']:.0%} · "
                        f"freshness {estimate['freshness']:.0%} · {observed} · {estimate['status']}"
                    )
                self._render_confidence_factors(estimate.get("source_factors") or {})
        if signals:
            imgui.separator()
            imgui.text("FOREIGN MOBILIZATION SIGNALS")
            for signal in signals:
                target = signal["target_country_name"] or signal["target_country_id"]
                if signal["status"] == "outdated":
                    imgui.text(f"{target}: outdated {signal['domain']} readiness signal")
                else:
                    imgui.text(
                        f"{target}: {signal['domain'].title()} readiness signal "
                        f"({signal['from_readiness']} → {signal['to_readiness']})"
                    )
                imgui.text_disabled(
                    f"Source {signal['source_country_id']} ({signal['source_type']}) · "
                    f"confidence {signal['confidence']:.0%} · "
                    f"freshness {signal['freshness']:.0%} · t={signal['observed_at_minute']}"
                )
                self._render_confidence_factors(signal.get("source_factors") or {})

    def _render_confidence_factors(self, factors: dict) -> None:
        factor_labels = []
        if "observer_telecom" in factors:
            factor_labels.append(f"observer telecom {factors['observer_telecom']:.0%}")
        if "target_telecom" in factors:
            factor_labels.append(f"target telecom {factors['target_telecom']:.0%}")
        if factors.get("intelligence_coverage"):
            factor_labels.append(f"intelligence coverage {factors['intelligence_coverage']}")
        if factor_labels:
            imgui.text_disabled("Confidence factors: " + " · ".join(factor_labels))
