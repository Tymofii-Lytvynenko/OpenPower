"""Native input fixture feeding the production map-movement request port."""
from src.client.controllers.unit_interaction_controller import UnitInteractionController
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.layouts.game_layout import GameLayout


def build_unit_movement_surface(state, client, context, settings, window, navigation, viewport):
    layout = GameLayout(client, context.target_tag, viewport, settings, window)
    selection = UnitInteractionController(None, None, client, on_move_requested=layout.unit_move_orders.request)

    def draw():
        with WindowManager.window("Map movement request input", x=30, y=100, w=220, h=180,
                                  closable=False, test_id="map.move.fixture"):
            for identity, region, country, lat, lon in (("unit-1", 2, "POL", 52., 21.),
                                                       ("unit-2", 2, "POL", 52.1, 21.1),
                                                       ("unit-2", 3, "DEU", 51., 13.),
                                                       ("unit-1", 1, "UKR", 50., 30.)):
                if imgui.button(identity + " -> " + country, test_id=f"map.move.{identity}.{country}"):
                    selection.move_units_to_target({identity}, region, lat, lon)
        layout.render(context.selected_region_id, 60., navigation, state)

    return draw
