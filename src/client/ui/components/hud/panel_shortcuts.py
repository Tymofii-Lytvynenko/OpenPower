"""Source-game panel shortcuts shared by the live HUD and UI scenarios."""
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.instrumented_imgui import imgui


PANEL_SHORTCUTS = (
    ("l", "UNIT_LIST", "unit_list.panel"),
    ("d", "UNIT_RESERVES", "unit_reserves.panel"),
    ("u", "UNIT_PRODUCTION", "unit_production.panel"),
    ("c", "COVERT_OPS", "covert_ops.panel"),
    ("w", "WAR_LIST", "war_list.panel"),
    ("b", "BUDGET", "budget.panel"),
    ("r", "RESOURCES", "resources.panel"),
    ("t", "TREATIES", "treaties.panel"),
)


def consume_panel_shortcuts(manager) -> None:
    io = imgui.get_io()
    if io.want_text_input or io.key_ctrl or io.key_alt or io.key_super:
        return
    if imgui.is_popup_open("", imgui.PopupFlags_.any_popup_id):
        return
    for key, panel_id, region_id in PANEL_SHORTCUTS:
        if imgui.is_key_pressed(getattr(imgui.Key, key), False):
            # Hiding a panel directly would bypass its unsaved-change dialog.
            if manager.is_visible(panel_id):
                WindowManager.request_close(region_id)
            else:
                manager.set_visible(panel_id, True)
