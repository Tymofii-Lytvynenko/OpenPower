from __future__ import annotations

from imgui_bundle import imgui

from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.shared.panel_widgets import draw_key_value_rows


class ConsolePanel:
    def render(self, state, context: PanelRenderContext) -> bool:
        with WindowManager.window("CONSOLE", x=80, y=520, w=720, h=320) as is_open:
            if not is_open:
                return False
            self._render_content(state, context)
            return True

    def _render_content(self, state, context: PanelRenderContext) -> None:
        draw_key_value_rows(
            (
                ("DATE", state.time.date_str),
                ("TARGET", context.target_tag),
                ("TABLES", str(len(state.tables))),
                ("EVENTS", str(len(state.events))),
                ("ACTIONS", str(len(state.current_actions))),
                ("DOMAIN LOG", str(len(state.journal.domain_events))),
                ("COMMAND LOG", str(len(state.journal.command_results))),
            )
        )
        imgui.separator()

        if not imgui.begin_table("console_tables", 3, imgui.TableFlags_.borders | imgui.TableFlags_.row_bg | imgui.TableFlags_.scroll_y, (0.0, 0.0)):
            return

        imgui.table_setup_column("TABLE")
        imgui.table_setup_column("ROWS", imgui.TableColumnFlags_.width_fixed, 90.0)
        imgui.table_setup_column("COLUMNS", imgui.TableColumnFlags_.width_fixed, 90.0)
        imgui.table_headers_row()

        table_meta = sorted(
            ((name, len(df), len(df.columns)) for name, df in state.tables.items()),
            key=lambda item: item[1],
            reverse=True,
        )
        for name, row_count, column_count in table_meta:
            imgui.table_next_row()
            imgui.table_next_column()
            imgui.text(name)
            imgui.table_next_column()
            imgui.text(str(row_count))
            imgui.table_next_column()
            imgui.text(str(column_count))

        imgui.end_table()
