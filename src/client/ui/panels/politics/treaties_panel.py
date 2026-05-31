from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.panels.politics.presenter import PoliticsPresenter
from src.client.ui.panels.shared.panel_data import format_side_names
from src.client.ui.panels.shared.panel_widgets import draw_empty_state, draw_required_tables


class TreatiesPanel:
    def __init__(self, open_editor_cb=None):
        self._presenter = PoliticsPresenter()
        self._open_editor_cb = open_editor_cb

    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("TREATIES", x=320, y=160, w=720, h=500) as is_open:
            if not is_open:
                return False
            self._render_content(state, context.target_tag, context.is_own_country)
            return True

    def _render_content(self, state, country_tag: str, is_own_country: bool) -> None:
        active_treaties = self._presenter.active_treaties_for_country(state, country_tag)
        pending_treaties = self._presenter.pending_treaties_for_country(state, country_tag)

        draw_required_tables(state, ("countries_treaties", "pending_treaties", "countries_relations"))
        imgui.separator()

        imgui.text_colored(GAMETHEME.colors.text_main, f"Active treaties: {len(active_treaties)}")
        imgui.same_line()
        imgui.text_disabled(f"Pending proposals: {len(pending_treaties)}")
        if is_own_country and self._open_editor_cb:
            imgui.same_line()
            if imgui.button("NEW TREATY", (110.0, 0.0)):
                self._open_editor_cb()

        imgui.dummy((0.0, 6.0))
        Prims.header("ACTIVE TREATIES", show_bg=False)
        if not active_treaties:
            draw_empty_state("No active treaties involve the selected country.")
        else:
            self._draw_active_treaties(state, active_treaties)

        imgui.dummy((0.0, 12.0))
        Prims.header("PENDING PROPOSALS", show_bg=False)
        if not pending_treaties:
            draw_empty_state("No pending treaty proposals are waiting for review.")
        else:
            for row in pending_treaties:
                title = str(row.get("title") or row.get("treaty_type") or "Proposal")
                status = str(row.get("status") or "pending").upper()
                imgui.text_colored(GAMETHEME.colors.text_main, title)
                imgui.same_line()
                Prims.right_align_text(status, GAMETHEME.colors.warning)
                imgui.text_disabled(
                    f"{row.get('source_country_id', '')} -> {row.get('target_country_id', '')}"
                )
                imgui.separator()

    def _draw_active_treaties(self, state, active_treaties: list[dict]) -> None:
        flags = imgui.TableFlags_.borders | imgui.TableFlags_.row_bg | imgui.TableFlags_.scroll_y | imgui.TableFlags_.sizing_stretch_prop
        if not imgui.begin_table("treaties_table", 4, flags, (0.0, 220.0)):
            return

        imgui.table_setup_column("NAME")
        imgui.table_setup_column("TYPE", imgui.TableColumnFlags_.width_fixed, 150.0)
        imgui.table_setup_column("MEMBERS", imgui.TableColumnFlags_.width_fixed, 90.0)
        imgui.table_setup_column("RELATIONS", imgui.TableColumnFlags_.width_fixed, 90.0)
        imgui.table_headers_row()

        for row in active_treaties:
            imgui.table_next_row()
            imgui.table_next_column()
            treaty_name = str(row.get("name") or "")
            member_names = format_side_names(state, row.get("members"))
            imgui.text(treaty_name)
            imgui.text_disabled(member_names)
            imgui.table_next_column()
            imgui.text(str(row.get("type") or "").replace("_", " ").title())
            imgui.table_next_column()
            imgui.text(str(row.get("members_count") or 0))
            imgui.table_next_column()
            imgui.text(f"{float(row.get('relation_score') or 0.0):.0f}")

        imgui.end_table()
