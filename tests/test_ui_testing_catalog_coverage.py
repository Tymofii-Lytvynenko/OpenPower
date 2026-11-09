from contextlib import nullcontext
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl
import pytest

from src.client.ui.testing import catalog


def _build(name, state=None, fixture=None):
    state = state or SimpleNamespace(tables={}, globals={})
    client = SimpleNamespace()
    context = SimpleNamespace(target_tag="USA", selected_region_id=2)
    settings = SimpleNamespace()
    window = SimpleNamespace(get_size=lambda: (1280, 720), game_config=object())
    navigation = SimpleNamespace(
        requests=[],
        show_main_menu=Mock(),
        show_load_game_screen=Mock(),
        load_saved_game=Mock(),
    )
    viewport = SimpleNamespace(requests=[])
    draw = catalog.build_surface(
        name, state, client, context, settings, window, navigation, viewport, fixture,
    )
    return draw, SimpleNamespace(
        state=state, client=client, context=context, settings=settings,
        window=window, navigation=navigation, viewport=viewport,
    )


class _FakeGameLayout:
    instances = []

    def __init__(self, *args, **kwargs):
        self.calls = []
        self.composer = object()
        self.unit_reorganization = SimpleNamespace(
            open_unit_list=Mock(), open_split=Mock(), open_merge=Mock(),
        )
        self.unit_move_orders = SimpleNamespace(request=Mock())
        self.on_move_selected_units = kwargs.get("on_move_selected_units")
        self.has_selected_units = kwargs.get("has_selected_units")
        self.instances.append(self)

    def render(self, *args):
        self.calls.append(("render", args))

    def dispatch_pending_navigation(self, navigation):
        self.calls.append(("dispatch", navigation))

    def show_context_menu(self, region_id):
        self.calls.append(("context", region_id))

    def select_battle_at(self, renderer, x, y, height):
        self.calls.append(("battle", renderer, x, y, height))


def test_surface_catalog_combines_registered_panels_and_layout_surfaces():
    manager, specs = catalog.panel_specs()
    surfaces = catalog.list_surfaces()
    by_id = {surface["id"]: surface for surface in surfaces}

    assert manager is not None and specs
    assert {"id", "title", "category"}.issubset(surfaces[0])
    assert all(name in by_id and by_id[name]["category"] == "layout" for name in catalog.EXTRA_SURFACES)
    assert all(surface["id"] == surface["id"].lower().replace("_", "-") for surface in surfaces)


def test_mini_map_variants_create_fixture_renderer_and_draw_tutorial(monkeypatch):
    mini_map_module = import_module("src.client.ui.components.hud.mini_map")
    tutorial_module = import_module("src.client.ui.components.guided_tutorial_window")
    panels = []
    tutorials = []

    class FakeMiniMap:
        def __init__(self, viewport, country, on_interaction=None):
            self.viewport, self.country, self.on_interaction = viewport, country, on_interaction
            panels.append(self)

        def render(self):
            self.viewport.focus_on_map_fraction(0.1, 0.2)
            self.viewport.focus_on_map_fraction(0.1, 0.2)
            self.viewport.set_zoom_fraction(0.5)
            self.viewport.set_zoom_fraction(1.5)

    class FakeTutorial:
        def __init__(self):
            self.open = Mock()
            self.render = Mock()
            self.on_interaction = Mock()
            tutorials.append(self)

    monkeypatch.setattr(mini_map_module, "MiniMapPanel", FakeMiniMap)
    monkeypatch.setattr(tutorial_module, "GuidedTutorialWindow", FakeTutorial)

    draw, parts = _build("mini_map")
    assert parts.viewport.renderer.map_data.packed_map.shape == (180, 360)
    assert set(parts.viewport.renderer.texture_manager.active_color_map) == {1, 2, 3}
    draw()
    assert parts.viewport.requests == [
        {"type": "focus_map", "x_fraction": 0.1, "y_fraction": 0.2},
        {"type": "zoom", "fraction": 1.0},
    ]
    assert panels[-1].on_interaction is None

    draw_tutorial, _ = _build("mini-map-tutorial")
    draw_tutorial()
    assert tutorials[-1].open.call_args.args == ("interface",)
    assert panels[-1].on_interaction == tutorials[-1].on_interaction
    assert tutorials[-1].render.called


@pytest.mark.parametrize(
    ("surface_name", "message"),
    [
        ("loading-error-load", "LoadGameTask failed"),
        ("loading-error-new", "NewGameTask failed"),
    ],
)
def test_loading_error_surfaces_report_failure_and_render_status(
    monkeypatch, surface_name, message,
):
    view_module = import_module("src.client.views.loading_view")
    status_module = import_module("src.client.ui.components.shared.loading_status_panel")
    composer_module = import_module("src.client.ui.core.composer")
    panels = []

    def worker(failure_state):
        try:
            failure_state.task.run()
        except RuntimeError as error:
            failure_state.error = error
            failure_state.on_failure(error)

    class FakeStatusPanel:
        def __init__(self):
            self.render = Mock()
            panels.append(self)

    class FakeComposer:
        def __init__(self, _theme):
            pass

    monkeypatch.setattr(view_module.LoadingView, "_worker", worker)
    monkeypatch.setattr(view_module.LoadingView, "on_update", lambda *_args: None)
    monkeypatch.setattr(status_module, "LoadingStatusPanel", FakeStatusPanel)
    monkeypatch.setattr(composer_module, "UIComposer", FakeComposer)

    draw, parts = _build(surface_name)
    assert parts.navigation.requests[0]["type"] == "loading_failure_reported"
    assert message in parts.navigation.requests[0]["message"]
    draw()
    assert panels[-1].render.called
    panels[-1].render.call_args.kwargs["on_return"]()
    parts.navigation.show_main_menu.assert_called_once()


def test_delegated_test_surfaces_forward_their_shared_context(monkeypatch):
    movement_module = import_module("src.client.ui.testing.unit_movement_surface")
    info_module = import_module("src.client.ui.testing.map_information_surface")
    movement = Mock(return_value="movement")
    information = Mock(return_value="information")
    monkeypatch.setattr(movement_module, "build_unit_movement_surface", movement)
    monkeypatch.setattr(info_module, "build_map_information_surface", information)

    draw, parts = _build("unit_movement")
    info_draw, info_parts = _build("map-information")

    assert draw == "movement"
    assert movement.call_args.args == (
        parts.state, parts.client, parts.context, parts.settings,
        parts.window, parts.navigation, parts.viewport,
    )
    assert info_draw == "information"
    assert information.call_args.args == (info_parts.state, info_parts.client, "USA")


def test_map_layout_surfaces_dispatch_context_orders_and_battle_markers(monkeypatch):
    _FakeGameLayout.instances.clear()
    layout_module = import_module("src.client.ui.layouts.game_layout")
    editor_module = import_module("src.client.ui.layouts.editor_layout")
    camera_module = import_module("src.client.controllers.camera_controller")
    battle_module = import_module("src.client.renderers.battle_effect_renderer")
    imgui_module = import_module("src.client.ui.core.instrumented_imgui")
    containers_module = import_module("src.client.ui.core.containers")
    monkeypatch.setattr(layout_module, "GameLayout", _FakeGameLayout)

    class FakeEditorLayout:
        def __init__(self, *_args):
            self.render = Mock()

    class FakeCamera:
        def __init__(self):
            self.look_at_pixel_coords = Mock()
            self.update_matrices = Mock()

    class FakeBattleRenderer:
        def __init__(self, *_args):
            self.last_layout = [SimpleNamespace(
                label_x=2, label_y=3, battle_id="b1", label="Battle",
            )]
            self.render = Mock()

    class FakeWindowManager:
        @staticmethod
        def window(*_args, **_kwargs):
            return nullcontext()

    fake_imgui = SimpleNamespace(
        WindowFlags_=SimpleNamespace(no_decoration=1, no_background=2, no_bring_to_front_on_focus=4),
        get_io=lambda: SimpleNamespace(display_size=SimpleNamespace(x=800, y=600)),
        set_cursor_screen_pos=Mock(),
        invisible_button=Mock(return_value=True),
        get_mouse_pos=lambda: SimpleNamespace(x=20, y=30),
    )
    monkeypatch.setattr(editor_module, "EditorLayout", FakeEditorLayout)
    monkeypatch.setattr(camera_module, "CameraController", FakeCamera)
    monkeypatch.setattr(battle_module, "BattleEffectRenderer", FakeBattleRenderer)
    monkeypatch.setattr(imgui_module, "imgui", fake_imgui)
    monkeypatch.setattr(containers_module, "WindowManager", FakeWindowManager)

    state = SimpleNamespace(
        tables={"regions": pl.DataFrame({
            "id": [2], "latitude": [45.0], "longitude": [32.0],
        })},
        globals={"ui_context_selected_units": ["u1"], "ui_context_region_id": 2},
    )
    draw_hud, parts = _build("game-hud", state)
    draw_context, _ = _build("map-context", state)
    draw_battle, _ = _build("battle-map", state)
    draw_editor, _ = _build("editor-hud", state)
    draw_hud()
    for _ in range(4):
        draw_context()
    context_layout = _FakeGameLayout.instances[-2]
    battle_layout = _FakeGameLayout.instances[-1]
    context_layout.on_move_selected_units()
    draw_battle()
    draw_editor()

    assert context_layout.has_selected_units() is True
    assert context_layout.unit_move_orders.request.call_args.args == ({"u1"}, 2, 45.0, 32.0)
    assert ("context", 2) in context_layout.calls
    assert _FakeGameLayout.instances[0].calls[-1][0] == "dispatch"
    assert any(call[0] == "battle" for call in battle_layout.calls)
    assert fake_imgui.invisible_button.called
    assert parts.navigation.requests == []

    for missing_regions in (
        None,
        pl.DataFrame({"id": [1]}),
        pl.DataFrame({"id": [2]}),
    ):
        tables = {} if missing_regions is None else {"regions": missing_regions}
        missing_state = SimpleNamespace(
            tables=tables,
            globals={"ui_context_region_id": 2},
        )
        _build("map-context", missing_state)
        _FakeGameLayout.instances[-1].on_move_selected_units()


def test_map_mode_surfaces_and_context_menu_navigation(monkeypatch):
    _FakeGameLayout.instances.clear()
    layout_module = import_module("src.client.ui.layouts.game_layout")
    gradient_module = import_module("src.client.visualization.map_modes.gradient_mode")
    empire_module = import_module("src.client.visualization.map_modes.empire_mode")
    monkeypatch.setattr(layout_module, "GameLayout", _FakeGameLayout)
    monkeypatch.setattr(gradient_module, "GradientMapMode", lambda *args, **kwargs: (args, kwargs))
    monkeypatch.setattr(empire_module, "EmpireMapMode", lambda: "empire")

    legend, _ = _build("map-legend", SimpleNamespace(tables={}, globals={"ui_map_mode": "gdp_total"}))
    navigation, _ = _build("map-mode-navigation")
    legend()
    for _ in range(4):
        navigation()

    assert _FakeGameLayout.instances[0].calls[0][0] == "render"
    assert ("context", 1) in _FakeGameLayout.instances[1].calls


def test_unit_and_menu_surfaces_exercise_dialog_callbacks(monkeypatch):
    _FakeGameLayout.instances.clear()
    layout_module = import_module("src.client.ui.layouts.game_layout")
    menu_module = import_module("src.client.ui.components.hud.unit_context_menu")
    prompt_module = import_module("src.client.ui.components.hud.unit_order_targeting_prompt")
    details_module = import_module("src.client.ui.panels.unit_details_window")
    main_module = import_module("src.client.ui.components.main_menu_content")
    settings_module = import_module("src.client.ui.components.settings_content")
    save_module = import_module("src.client.ui.components.shared.save_game_dialog")
    composer_module = import_module("src.client.ui.core.composer")
    monkeypatch.setattr(layout_module, "GameLayout", _FakeGameLayout)
    unit_menus, prompts, details, main_menus, dialogs = [], [], [], [], []

    class FakeUnitMenu:
        def __init__(self, *_args, **_kwargs):
            self.show = Mock()
            self.render = Mock()
            unit_menus.append(self)

    class FakePrompt:
        def __init__(self):
            self.render = Mock()
            prompts.append(self)

    class FakeDetails:
        def __init__(self):
            self.open_for_unit = Mock()
            self.render = Mock()
            details.append(self)

    class FakeComposer:
        def __init__(self, *_args):
            pass

    class FakeSettings:
        def __init__(self, *_args, **_kwargs):
            pass

    class FakeSaveDialog:
        def __init__(self, list_saves, save, load, notify):
            self.list_saves, self.save, self.load, self.notify = list_saves, save, load, notify
            self.toggle = Mock()
            self.render = Mock()
            dialogs.append(self)

    class FakeMainMenu:
        def __init__(self, _composer, _settings, actions):
            self.actions = actions
            self.render = Mock()
            main_menus.append(self)

    monkeypatch.setattr(menu_module, "UnitContextMenu", FakeUnitMenu)
    monkeypatch.setattr(prompt_module, "UnitOrderTargetingPrompt", FakePrompt)
    monkeypatch.setattr(details_module, "UnitDetailsWindow", FakeDetails)
    monkeypatch.setattr(composer_module, "UIComposer", FakeComposer)
    monkeypatch.setattr(settings_module, "GameSettingsContent", FakeSettings)
    monkeypatch.setattr(save_module, "SaveGameDialog", FakeSaveDialog)
    monkeypatch.setattr(main_module, "MainMenuContent", FakeMainMenu)
    action_callbacks = {}

    def build_actions(_new_game, open_load, _quit):
        action_callbacks["open_load"] = open_load
        return action_callbacks

    monkeypatch.setattr(main_module, "build_main_menu_actions", build_actions)

    draw_unit, _ = _build("unit-context")
    draw_details, parts = _build("unit-details")
    draw_menu, menu_parts = _build("main-menu", fixture={"saved_games": ["save-1"]})
    for _ in range(4):
        draw_unit()
    draw_details()
    action_callbacks["open_load"]()
    draw_menu()
    dialogs[-1].load("save-1")
    draw_menu()

    assert unit_menus[-1].show.call_args.args == ("unit-1",)
    assert prompts[-1].render.called
    assert details[-1].open_for_unit.call_args.args == ("unit-1",)
    assert dialogs[-1].list_saves() == ["save-1"]
    menu_parts.navigation.show_load_game_screen.assert_called_once()
    menu_parts.navigation.load_saved_game.assert_called_once_with(menu_parts.window.game_config, "save-1")
    assert dialogs[-1].render.called and main_menus[-1].render.called


def test_multiplayer_surface_callbacks_emit_navigation_requests(monkeypatch):
    module = import_module("src.client.ui.components.shared.multiplayer_windows")
    dialogs = []

    class FakeInputDialog:
        def __init__(self):
            dialogs.append(self)

        def show(self, title, on_submit, password):
            self.title, self.on_submit, self.password = title, on_submit, password

        def render(self, *_args):
            self.rendered = True

    class FakeServerInfoWindow:
        def __init__(self):
            dialogs.append(self)

        def show(self, server, on_join):
            self.server, self.on_join = server, on_join

        def render(self, *_args):
            self.rendered = True

    monkeypatch.setattr(module, "GenericInputDialog", FakeInputDialog)
    monkeypatch.setattr(module, "ServerInfoWindow", FakeServerInfoWindow)

    input_draw, input_parts = _build("multiplayer-input-dialog")
    server_draw, server_parts = _build("multiplayer-server-info")
    input_draw()
    server_draw()
    dialogs[0].on_submit("secret")
    dialogs[1].on_join()

    assert dialogs[0].title == "PASSWORD" and dialogs[0].password is True
    assert dialogs[0].rendered and dialogs[1].rendered
    assert input_parts.navigation.requests == [{
        "type": "multiplayer_password_submitted", "value": "secret",
    }]
    assert server_parts.navigation.requests == [{
        "type": "multiplayer_server_join_requested",
    }]


def test_new_game_selection_wires_scenario_country_profile_and_party_flow(monkeypatch):
    selection_module = import_module("src.client.views.new_game_view")
    scenario_module = import_module("src.client.ui.components.shared.campaign_scenario_selection_window")
    profile_module = import_module("src.client.ui.components.shared.country_profile_window")
    party_module = import_module("src.client.ui.components.shared.party_selection_window")
    setup_module = import_module("src.client.ui.components.shared.single_player_setup_window")
    objects = {}

    class FakeWindow:
        def __init__(self, *args, **kwargs):
            self.show = Mock()
            objects[self.__class__.__name__] = self

    class FakePartyWindow(FakeWindow):
        @staticmethod
        def default_party_id(_state, country_id):
            return f"party-{country_id.lower()}"

    monkeypatch.setattr(scenario_module, "CampaignScenarioSelectionWindow", FakeWindow)
    monkeypatch.setattr(profile_module, "CountryProfileWindow", FakeWindow)
    monkeypatch.setattr(party_module, "PartySelectionWindow", FakePartyWindow)
    monkeypatch.setattr(setup_module, "SinglePlayerSetupWindow", FakeWindow)

    def render_ui(new_game):
        new_game._select_scenario("scenario-2")
        new_game._open_country_profile(new_game)
        new_game._select_country("")
        new_game._select_country("CAN")
        new_game._open_party_selection(new_game)
        new_game._enter_country_setup()
        new_game._return_to_scenario_selection()

    monkeypatch.setattr(selection_module.NewGameView, "_render_ui", staticmethod(render_ui))
    state = SimpleNamespace(
        tables={
            "countries": pl.DataFrame({"id": ["USA", "CAN"], "is_playable": [True, True]}),
            "campaign_scenarios": pl.DataFrame([
                {"id": "scenario-1", "selectable_country_ids_json": '["USA"]'},
                {"id": "scenario-2", "selectable_country_ids_json": '["CAN"]'},
            ]),
        },
        globals={},
    )

    draw, _ = _build("new-game-selection", state)
    draw()

    assert objects["FakeWindow"].show.called
    assert objects["FakePartyWindow"].show.called


def test_registered_panel_surface_and_unknown_name_contract(monkeypatch):
    class FakeManager:
        def __init__(self):
            self.registered = []
            self.visible = []
            self.render_all = Mock(return_value="rendered")

        def register_spec(self, spec):
            self.registered.append(spec)

        def set_visible(self, name, visible):
            self.visible.append((name, visible))

    manager = FakeManager()
    spec = SimpleNamespace(id="BUDGET_PANEL", title="Budget", category="economy")
    monkeypatch.setattr(catalog, "panel_specs", lambda *_args: (manager, [spec]))

    draw, parts = _build("budget-panel")
    assert manager.registered == [spec]
    assert manager.visible == [("BUDGET_PANEL", True)]
    assert draw() == "rendered"
    manager.render_all.assert_called_once_with(parts.state, parts.context)

    monkeypatch.setattr(catalog, "panel_specs", lambda *_args: (manager, []))
    with pytest.raises(ValueError, match="Unknown UI surface: missing"):
        _build("missing")
