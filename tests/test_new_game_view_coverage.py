from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import arcade
import polars as pl

from src.client.views import new_game_view as view_module
from src.client.views.new_game_view import NewGameView


def view_stub(state=None):
    state = state or SimpleNamespace(tables={})
    context = SimpleNamespace(
        DEPTH_TEST="depth",
        BLEND="blend",
        scissor="old",
        viewport=None,
        enable_only=Mock(),
    )
    window = SimpleNamespace(
        get_size=Mock(return_value=(1280, 720)),
        ctx=context,
        session=SimpleNamespace(),
    )
    view = SimpleNamespace(
        session=SimpleNamespace(map_data=SimpleNamespace(width=100, height=50)),
        config=Mock(),
        net=SimpleNamespace(get_state=Mock(return_value=state)),
        ui=SimpleNamespace(setup_frame=Mock()),
        setup_stage="scenario",
        scenario_selection_window=Mock(),
        single_player_setup_window=Mock(),
        country_profile_window=Mock(),
        party_selection_window=Mock(),
        playable_countries=pl.DataFrame({"id": ["USA"]}),
        all_playable_countries=pl.DataFrame({"id": ["USA"]}),
        campaign_scenarios=[],
        selected_scenario_id=None,
        selected_country_id=None,
        selected_party_id="",
        renderer=Mock(),
        cam_ctrl=SimpleNamespace(
            min_distance=1.0,
            max_distance=3.0,
            distance=2.0,
            look_at_pixel_coords=Mock(),
            drag=Mock(),
            zoom_scroll=Mock(),
        ),
        nav=Mock(),
        window=window,
        clear=Mock(),
        imgui=SimpleNamespace(
            new_frame=Mock(),
            render=Mock(),
        ),
        _render_ui=Mock(),
    )
    for method_name in (
        "_selected_scenario", "_select_scenario", "_enter_country_setup",
        "_return_to_scenario_selection", "_return_to_main_menu", "_select_country",
        "_select_party", "_open_country_profile", "_open_party_selection",
        "_start_game", "_apply_country_selection_zoom",
    ):
        setattr(view, method_name, MethodType(getattr(NewGameView, method_name), view))
    return view


def test_init_composes_shared_renderer_and_loads_initial_campaign_state(monkeypatch):
    state = SimpleNamespace(
        tables={
            "countries": pl.DataFrame({
                "id": ["USA", "CAN", "MEX"],
                "is_playable": [True, True, False],
            }),
            "campaign_scenarios": pl.DataFrame({
                "id": ["country", "disabled"],
                "enabled": [True, False],
                "selectable_country_ids_json": ['["USA"]', "[]"],
            }),
            "regions": pl.DataFrame({"id": [1, 2], "owner": ["USA", "CAN"]}),
        },
    )
    state.get_table = lambda name: state.tables[name]
    shared_renderer = Mock()
    shared_renderer.camera = Mock()
    window = SimpleNamespace(shared_renderer=shared_renderer)
    session = SimpleNamespace(map_data=SimpleNamespace(width=100, height=50))
    network = Mock()
    network.get_state.return_value = state
    monkeypatch.setattr(view_module.BaseImGuiView, "__init__", lambda self: setattr(self, "_test_window", window))
    monkeypatch.setattr(NewGameView, "window", property(lambda self: self._test_window), raising=False)
    monkeypatch.setattr(view_module, "UIComposer", lambda _theme: Mock())
    monkeypatch.setattr(view_module, "NetworkClient", lambda _session: network)
    monkeypatch.setattr(view_module, "CampaignScenarioSelectionWindow", Mock)
    monkeypatch.setattr(view_module, "SinglePlayerSetupWindow", Mock)
    monkeypatch.setattr(view_module, "CountryProfileWindow", lambda _callback: Mock())

    class PartyWindow:
        def __init__(self, callback):
            self.callback = callback

        @staticmethod
        def default_party_id(_state, _country):
            return "party-1"

        @staticmethod
        def party_options(_state, _country):
            return []

    monkeypatch.setattr(view_module, "PartySelectionWindow", PartyWindow)
    monkeypatch.setattr(view_module, "generate_political_colors", lambda owners: {owner: (1, 2, 3) for owner in owners})

    view = NewGameView(session, Mock())

    assert view.setup_stage == "scenario"
    assert view.selected_country_id is None
    assert view.selected_scenario_id == "country"
    assert view.playable_countries["id"].to_list() == ["USA"]
    assert view.all_playable_countries["id"].to_list() == ["CAN", "USA"]
    shared_renderer.set_overlay_style.assert_called_once_with(enabled=True, opacity=0.0)
    shared_renderer.update_overlay.assert_called_once_with({1: (1, 2, 3), 2: (1, 2, 3)})
    shared_renderer.clear_highlight.assert_called_once_with()


def test_init_uses_fallback_renderer_when_window_has_no_shared_renderer(monkeypatch):
    import src.client.controllers.camera_controller as camera_module
    import src.client.renderers.map_renderer as map_module

    state = SimpleNamespace(tables={})
    state.get_table = lambda _name: (_ for _ in ()).throw(KeyError("missing"))
    window = SimpleNamespace(shared_renderer=None)
    session = SimpleNamespace(map_data=object())
    network = Mock()
    network.get_state.return_value = state
    fallback_renderer = Mock()
    fallback_camera = Mock()
    monkeypatch.setattr(view_module.BaseImGuiView, "__init__", lambda self: setattr(self, "_test_window", window))
    monkeypatch.setattr(NewGameView, "window", property(lambda self: self._test_window), raising=False)
    monkeypatch.setattr(view_module, "UIComposer", lambda _theme: Mock())
    monkeypatch.setattr(view_module, "NetworkClient", lambda _session: network)
    monkeypatch.setattr(view_module, "CampaignScenarioSelectionWindow", Mock)
    monkeypatch.setattr(view_module, "SinglePlayerSetupWindow", Mock)
    monkeypatch.setattr(view_module, "CountryProfileWindow", lambda _callback: Mock())
    monkeypatch.setattr(view_module, "PartySelectionWindow", lambda _callback: Mock())
    monkeypatch.setattr(map_module, "MapRenderer", lambda **_kwargs: fallback_renderer)
    monkeypatch.setattr(camera_module, "CameraController", lambda: fallback_camera)

    view = NewGameView(session, Mock(get_asset_path=lambda path: f"asset:{path}"))

    assert view.renderer is fallback_renderer
    assert view.cam_ctrl is fallback_camera
    fallback_renderer.set_overlay_style.assert_called_once_with(enabled=True, opacity=0.0)
    fallback_renderer.update_overlay.assert_not_called()
    assert view.playable_countries.is_empty()
    assert view.campaign_scenarios == []


def test_refresh_map_handles_missing_tables_columns_and_builds_palette(monkeypatch):
    view = view_stub()
    NewGameView._refresh_political_map(view)

    view.net.get_state.return_value = SimpleNamespace(tables={"regions": pl.DataFrame({"id": [1]})})
    view.net.get_state.return_value.get_table = lambda name: view.net.get_state.return_value.tables[name]
    NewGameView._refresh_political_map(view)
    view.renderer.update_overlay.assert_not_called()

    state = SimpleNamespace(
        tables={"regions": pl.DataFrame({"id": [1, 2, 3], "owner": ["USA", "CAN", "UNK"]})},
    )
    state.get_table = lambda name: state.tables[name]
    view.net.get_state.return_value = state
    monkeypatch.setattr(view_module, "generate_political_colors", lambda owners: {"USA": (1, 2, 3)})

    NewGameView._refresh_political_map(view)

    assert view.renderer.update_overlay.call_args.args[0] == {
        1: (1, 2, 3), 2: tuple(int(value * 255) for value in view_module.GAMETHEME.colors.text_dim[:3]),
        3: tuple(int(value * 255) for value in view_module.GAMETHEME.colors.text_dim[:3]),
    }


def test_refresh_map_swallows_state_and_renderer_errors(monkeypatch, capsys):
    view = view_stub()
    view.net.get_state.side_effect = RuntimeError("unavailable")

    NewGameView._refresh_political_map(view)

    assert "Color Generation Error: unavailable" in capsys.readouterr().out

    view.net.get_state.side_effect = None
    state = SimpleNamespace(tables={"regions": pl.DataFrame({"id": [1], "owner": ["USA"]})})
    state.get_table = lambda name: state.tables[name]
    view.net.get_state.return_value = state
    view.renderer.update_overlay.side_effect = ValueError("renderer")
    NewGameView._refresh_political_map(view)
    assert "Color Generation Error: renderer" in capsys.readouterr().out


def test_country_and_scenario_fetchers_handle_missing_and_enabled_records():
    view = view_stub()
    view.net.get_state.side_effect = KeyError("countries")
    assert NewGameView._fetch_playable_countries(view).is_empty()

    view.net.get_state.side_effect = None
    countries = pl.DataFrame({
        "id": ["USA", "CAN", "MEX"],
        "is_playable": [True, False, None],
    })
    state = SimpleNamespace(tables={"countries": countries})
    state.get_table = lambda name: state.tables[name]
    view.net.get_state.return_value = state
    assert NewGameView._fetch_playable_countries(view)["id"].to_list() == ["MEX", "USA"]

    state.tables["campaign_scenarios"] = pl.DataFrame({
        "id": ["one", "off"], "enabled": [True, False],
    })
    assert NewGameView._fetch_campaign_scenarios(view) == [{"id": "one", "enabled": True}]
    state.tables["campaign_scenarios"] = pl.DataFrame()
    assert NewGameView._fetch_campaign_scenarios(view) == []
    view.net.get_state.return_value = SimpleNamespace()
    assert NewGameView._fetch_campaign_scenarios(view) == []


def test_scenario_selection_filters_countries_and_clears_invalid_selection():
    view = view_stub()
    view.all_playable_countries = pl.DataFrame({"id": ["USA", "CAN", "MEX"]})
    view.campaign_scenarios = [
        {"id": "north", "selectable_country_ids_json": '["CAN", "USA"]'},
        {"id": "south", "selectable_country_ids_json": '["MEX"]'},
    ]
    view.selected_scenario_id = "north"
    view.selected_country_id = "CAN"
    assert NewGameView._selected_scenario(view) == view.campaign_scenarios[0]

    NewGameView._select_scenario(view, "south")
    assert view.playable_countries["id"].to_list() == ["MEX"]
    assert view.selected_country_id is None

    view.selected_country_id = "MEX"
    NewGameView._select_scenario(view, "unknown")
    assert view.playable_countries["id"].to_list() == ["USA", "CAN", "MEX"]
    assert view.selected_country_id == "MEX"
    assert NewGameView._selected_scenario(view) is None


def test_render_ui_routes_scenario_and_country_setup_callbacks(monkeypatch):
    state = SimpleNamespace(tables={})
    view = view_stub(state)
    view.campaign_scenarios = [{"id": "start"}]
    view.selected_scenario_id = "start"

    NewGameView._render_ui(view)

    args = view.scenario_selection_window.render.call_args.args
    assert args[:4] == (1280, 720, view.campaign_scenarios, "start")
    args[4]("start")
    args[5]()
    assert view.setup_stage == "country"
    args[6]()
    view.renderer.clear_highlight.assert_called_once_with()
    view.renderer.set_overlay_style.assert_called_once_with(enabled=False, opacity=0.0)
    view.nav.show_main_menu.assert_called_once_with(view.session, view.config)

    view = view_stub(state)
    view.setup_stage = "country"
    view.playable_countries = pl.DataFrame({"id": ["usa", "can"]})
    view.selected_country_id = "USA"
    view.selected_party_id = "p2"
    party_options = [
        {"party_id": "p1", "display_name": "One"},
        {"party_id": "p2", "display_name": "Two"},
    ]
    monkeypatch.setattr(view_module, "resolve_country_name", lambda _state, tag: f"Name {tag}")
    monkeypatch.setattr(view_module.PartySelectionWindow, "party_options", staticmethod(lambda *_args: party_options))
    monkeypatch.setattr(view_module, "preview_campaign_scenario", lambda scenario: ("preview", scenario))
    view.campaign_scenarios = [{"id": "start"}]
    view.selected_scenario_id = "start"

    NewGameView._render_ui(view)

    setup_args = view.single_player_setup_window.render.call_args.args
    assert setup_args[2] == [("USA", "USA - Name USA"), ("CAN", "CAN - Name CAN")]
    assert setup_args[3:6] == ("USA", "Two", True)
    assert setup_args[6] == ("preview", {"id": "start"})
    setup_args[8]()
    view.country_profile_window.show.assert_called_once_with(state, ["usa", "can"])
    setup_args[9]()
    view.country_profile_window.close.assert_called_once_with()
    view.party_selection_window.show.assert_called_once_with(state, "USA", "p2")
    view.country_profile_window.render.assert_called_once_with(1280, 720)
    view.party_selection_window.render.assert_called_once_with(1280, 720)


def test_stage_and_country_party_selection_callbacks(monkeypatch):
    view = view_stub()
    NewGameView._enter_country_setup(view)
    assert view.setup_stage == "country"
    NewGameView._return_to_scenario_selection(view)
    assert view.setup_stage == "scenario"

    NewGameView._open_country_profile(view, SimpleNamespace())
    view.country_profile_window.show.assert_called_once_with(SimpleNamespace(), ["USA"])
    NewGameView._open_party_selection(view, object())
    view.party_selection_window.show.assert_not_called()

    state = object()
    view.selected_country_id = "USA"
    view.selected_party_id = "p1"
    NewGameView._open_party_selection(view, state)
    view.country_profile_window.close.assert_called_once_with()
    view.party_selection_window.show.assert_called_once_with(state, "USA", "p1")

    monkeypatch.setattr(view_module.PartySelectionWindow, "default_party_id", staticmethod(lambda *_args: "default"))
    view._focus_camera_on_country = Mock()
    view._highlight_country = Mock()
    NewGameView._select_country(view, " can ")
    assert view.selected_country_id == "CAN"
    assert view.selected_party_id == "default"
    view._focus_camera_on_country.assert_called_once_with("CAN")
    view._highlight_country.assert_called_once_with("CAN")

    NewGameView._select_country(view, " ")
    assert view.selected_country_id is None
    assert view.selected_party_id == ""
    view.renderer.clear_highlight.assert_called_once_with()
    NewGameView._select_party(view, " party-2 ")
    assert view.selected_party_id == "party-2"


def test_highlighting_handles_missing_regions_valid_owner_and_bad_schema(capsys):
    view = view_stub()
    NewGameView._highlight_country(view, "USA")
    view.renderer.set_highlight.assert_not_called()

    state = SimpleNamespace(tables={
        "regions": pl.DataFrame({"id": [1, 2], "owner": ["USA", "CAN"]}),
    })
    view.net.get_state.return_value = state
    NewGameView._highlight_country(view, "USA")
    view.renderer.set_highlight.assert_called_once_with([1])

    state.tables["regions"] = pl.DataFrame({"id": [1]})
    NewGameView._highlight_country(view, "USA")
    assert "Highlight error:" in capsys.readouterr().out


def test_camera_focus_uses_owned_region_centroid_and_clamps_zoom(monkeypatch):
    view = view_stub(SimpleNamespace(tables={}))
    NewGameView._focus_camera_on_country(view, "USA")
    view.cam_ctrl.look_at_pixel_coords.assert_not_called()

    state = SimpleNamespace(tables={
        "regions": pl.DataFrame({"id": [1], "owner": ["USA"]}),
    })
    view.net.get_state.return_value = state
    monkeypatch.setattr(view_module, "calculate_centroid", lambda *_args: None)
    NewGameView._focus_camera_on_country(view, "USA")
    view.cam_ctrl.look_at_pixel_coords.assert_not_called()

    monkeypatch.setattr(view_module, "calculate_centroid", lambda *_args: (25.0, 10.0))
    NewGameView._focus_camera_on_country(view, "USA")
    view.cam_ctrl.look_at_pixel_coords.assert_called_once_with(25.0, 40.0, 100, 50)
    assert view.cam_ctrl.distance == view_module.COUNTRY_SELECTION_FOCUS_DISTANCE

    view.cam_ctrl.min_distance = 2.0
    view.cam_ctrl.max_distance = 3.0
    NewGameView._apply_country_selection_zoom(view)
    assert view.cam_ctrl.distance == 2.0
    view.cam_ctrl.min_distance = 1.0
    view.cam_ctrl.max_distance = 1.2
    NewGameView._apply_country_selection_zoom(view)
    assert view.cam_ctrl.distance == 1.2


def test_start_game_builds_task_and_navigates_with_success_context(monkeypatch):
    view = view_stub()
    NewGameView._start_game(view)
    view.nav.show_loading.assert_not_called()

    view.selected_country_id = "USA"
    view.selected_scenario_id = "scenario-1"
    task_module = __import__("src.client.tasks.new_game_task", fromlist=["NewGameTask"])
    task = Mock()
    task_factory = Mock(return_value=task)
    monkeypatch.setattr(task_module, "NewGameTask", task_factory)
    success_callbacks = []
    view.nav.show_loading.side_effect = lambda current, *, on_success: success_callbacks.append(on_success)
    NewGameView._start_game(view)

    task_factory.assert_called_once_with(
        view.window, view.config, "USA", "scenario-1", "",
    )
    view.nav.show_loading.assert_called_once_with(task, on_success=success_callbacks[0])
    new_session = object()
    success_callbacks[0](SimpleNamespace(
        session=new_session, player_tag="USA", start_pos=(10, 20),
    ))
    assert view.window.session is new_session
    view.nav.show_game_view.assert_called_once_with(
        session=new_session,
        config=view.config,
        player_tag="USA",
        initial_pos=(10, 20),
    )


def test_draw_and_mouse_events_forward_to_renderer_and_camera():
    view = view_stub()

    NewGameView.on_show_view(view)
    NewGameView.on_draw(view)

    view.clear.assert_called_once_with()
    assert view.window.ctx.scissor is None
    assert view.window.ctx.viewport == (0, 0, 1280, 720)
    view.window.ctx.enable_only.assert_called_once_with("depth", "blend")
    view.renderer.draw.assert_called_once_with()
    view._render_ui.assert_called_once_with()
    view.imgui.render.assert_called_once_with()

    NewGameView.on_game_mouse_drag(view, 0, 0, 2, 3, arcade.MOUSE_BUTTON_LEFT, 0)
    view.cam_ctrl.drag.assert_called_once_with(2, 3)
    NewGameView.on_game_mouse_drag(view, 0, 0, 2, 3, arcade.MOUSE_BUTTON_RIGHT, 0)
    assert view.cam_ctrl.drag.call_count == 1
    NewGameView.on_game_mouse_scroll(view, 0, 0, 1, -2)
    view.cam_ctrl.zoom_scroll.assert_called_once_with(-2)
