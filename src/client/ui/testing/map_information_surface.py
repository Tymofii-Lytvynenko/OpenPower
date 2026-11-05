"""Native map-information scenarios with deterministic projected hit targets."""
from types import SimpleNamespace

import arcade

from src.client.controllers.unit_interaction_controller import UnitInteractionController
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.panels.military.map_information_windows import MapInformationWindows


def build_map_information_surface(state, client, viewer):
    windows = MapInformationWindows(viewer)
    projected = {
        identity: SimpleNamespace(unit_id=identity, screen_x=x, screen_y=220, width=26, height=18)
        for identity, x in (("unit-1", 160), ("unit-2", 240), ("unit-foreign", 320))
    }
    renderer = SimpleNamespace(get_unit=projected.get)
    selection = UnitInteractionController(renderer, None, client)

    def render():
        flags = (imgui.WindowFlags_.no_decoration | imgui.WindowFlags_.no_bring_to_front_on_focus
                 | imgui.WindowFlags_.no_background)
        region_id = None
        with WindowManager.window("Map information input fixture", x=80, y=80, w=440, h=320,
                                  closable=False, flags=flags, test_id="map.info.fixture"):
            for identity, unit in projected.items():
                imgui.set_cursor_screen_pos((unit.screen_x - 13, 150))
                if imgui.button(identity, (70, 22), test_id="map.unit." + identity):
                    renderer.get_unit_at = lambda x, y, hit=unit: hit
                    selection.on_mouse_press(unit.screen_x, unit.screen_y, arcade.MOUSE_BUTTON_LEFT)
                    selection.on_mouse_release(unit.screen_x, unit.screen_y, arcade.MOUSE_BUTTON_LEFT)
            imgui.set_cursor_screen_pos((100, 250))
            if imgui.button("Deselect", test_id="map.units.clear"):
                selection.clear_selection()
            imgui.same_line()
            if imgui.button("Select two", test_id="map.units.multiple"):
                selection.selected_unit_ids = {"unit-1", "unit-2"}
            imgui.set_cursor_screen_pos((100, 300))
            imgui.button("Region 1", (150, 35), test_id="map.region.1")
            mouse = imgui.get_mouse_pos()
            # Map ray hits are independent of ImGui's Tab navigation hover mode.
            if 100 <= mouse.x <= 250 and 300 <= mouse.y <= 335:
                region_id = 1
            imgui.same_line()
            imgui.button("Ocean", (100, 35), test_id="map.ocean")
        height = imgui.get_io().display_size.y
        windows.render_selected_unit(state, selection.selected_unit_ids, projected.get, height)
        mouse = imgui.get_mouse_pos()
        windows.render_region(state, region_id, (mouse.x, mouse.y), active=imgui.is_key_down(imgui.Key.tab))

    return render
