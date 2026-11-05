"""Discover test surfaces from the same registry used by the production HUD."""
from __future__ import annotations

from src.client.ui.components.hud.panel_manager import PanelManager
from src.client.ui.layouts.game_panel_registry import build_game_panel_specs


EXTRA_SURFACES = (
    "game-hud", "battle-map", "map-information", "map-legend", "map-mode-navigation", "mini-map", "mini-map-tutorial", "unit-movement", "editor-hud", "map-context", "unit-context", "unit-details", "main-menu", "new-game-selection",
    "loading-error-load", "loading-error-new",
    "multiplayer-input-dialog", "multiplayer-server-info",
)


def panel_specs(settings=None, window=None):
    manager = PanelManager()
    specs = build_game_panel_specs(manager, settings, window)
    return manager, specs


def list_surfaces() -> list[dict]:
    _, specs = panel_specs()
    return [{"id": spec.id.lower().replace("_", "-"), "title": spec.title,
             "category": spec.category} for spec in specs] + [
        {"id": name, "title": name, "category": "layout"} for name in EXTRA_SURFACES
    ]


def build_surface(
    name, state, client, context, settings, window, navigation, viewport, fixture=None
):
    from src.client.ui.layouts.game_layout import GameLayout
    from src.client.ui.layouts.editor_layout import EditorLayout
    from src.client.ui.core.composer import UIComposer
    from src.client.ui.core.theme import GAMETHEME
    from src.client.ui.components.hud.unit_context_menu import UnitContextMenu
    from src.client.ui.components.hud.unit_order_targeting_prompt import UnitOrderTargetingPrompt
    from src.client.ui.components.main_menu_content import MainMenuContent, build_main_menu_actions
    from src.client.ui.components.settings_content import GameSettingsContent
    from src.client.ui.panels.unit_details_window import UnitDetailsWindow

    normalized = name.lower().replace("_", "-")
    if normalized in {"mini-map", "mini-map-tutorial"}:
        from types import SimpleNamespace
        import numpy as np
        from src.client.ui.components.hud.mini_map import MiniMapPanel

        height, width = 180, 360
        y, x = np.ogrid[:height, :width]
        packed_map = np.zeros((height, width), dtype=np.int32)
        land_a = ((x - 95) / 82) ** 2 + ((y - 55) / 52) ** 2 < 1
        land_b = ((x - 220) / 58) ** 2 + ((y - 75) / 40) ** 2 < 1
        land_c = ((x - 302) / 24) ** 2 + ((y - 126) / 21) ** 2 < 1
        packed_map[land_a] = 1
        packed_map[land_b] = 2
        packed_map[land_c] = 3
        map_data = SimpleNamespace(width=width, height=height, packed_map=packed_map)
        texture_manager = SimpleNamespace(
            active_color_map={
                1: (62, 133, 86),
                2: (91, 107, 172),
                3: (166, 127, 66),
            },
            overlay_revision=1,
        )
        viewport.renderer = SimpleNamespace(
            map_data=map_data,
            texture_manager=texture_manager,
            width=width,
            height=height,
            projection_mode="globe",
        )
        viewport.current_mode_key = "political"
        viewport.map_center_fraction = lambda: (0.5, 0.5)
        viewport.zoom_fraction = lambda: viewport._mini_map_zoom
        viewport._mini_map_zoom = 0.5

        def focus_map(x_fraction, y_fraction):
            request = {
                "type": "focus_map",
                "x_fraction": round(float(x_fraction), 4),
                "y_fraction": round(float(y_fraction), 4),
            }
            if not viewport.requests or viewport.requests[-1] != request:
                viewport.requests.append(request)

        def set_zoom(value):
            value = round(min(1.0, max(0.0, float(value))), 4)
            if value == viewport._mini_map_zoom:
                return
            viewport._mini_map_zoom = value
            viewport.requests.append({"type": "zoom", "fraction": value})

        viewport.focus_on_map_fraction = focus_map
        viewport.set_zoom_fraction = set_zoom
        tutorial = None
        if normalized == "mini-map-tutorial":
            from src.client.ui.components.guided_tutorial_window import GuidedTutorialWindow
            tutorial = GuidedTutorialWindow()
            tutorial.open("interface")
        panel = MiniMapPanel(
            viewport, context.target_tag,
            tutorial.on_interaction if tutorial is not None else None,
        )

        def draw_mini_map():
            panel.render()
            if tutorial is not None:
                tutorial.render(lambda _: False)

        return draw_mini_map
    if normalized in {"loading-error-load", "loading-error-new"}:
        from types import SimpleNamespace
        from src.client.ui.components.shared.loading_status_panel import LoadingStatusPanel
        from src.client.views.loading_view import LoadingView

        failure_message = (
            "LoadGameTask failed: save 'missing-session' is unavailable."
            if normalized == "loading-error-load" else
            "NewGameTask failed: the server refused campaign setup."
        )

        class FailedOperationTask:
            progress = 0.65
            status_text = "Synchronizing game state..."

            def run(self):
                raise RuntimeError(failure_message)

        task = FailedOperationTask()
        failure_state = SimpleNamespace(
            task=task,
            result=None,
            error=None,
            is_finished=False,
            _active=True,
            _failure_reported=False,
            _completion_started=False,
            on_failure=lambda error: navigation.requests.append({
                "type": "loading_failure_reported", "message": str(error),
            }),
            window=SimpleNamespace(imgui=SimpleNamespace(update_time=lambda _delta: None)),
        )
        LoadingView._worker(failure_state)
        LoadingView.on_update(failure_state, 1 / 60)

        status_panel = LoadingStatusPanel()
        loading_ui = UIComposer(GAMETHEME)

        def draw_loading_failure():
            status_panel.render(
                loading_ui, task, failure_state.error,
                window.get_size(), on_return=lambda: navigation.show_main_menu(None, window.game_config),
            )

        return draw_loading_failure
    if normalized == "unit-movement":
        from src.client.ui.testing.unit_movement_surface import build_unit_movement_surface
        return build_unit_movement_surface(state, client, context, settings, window, navigation, viewport)
    if normalized == "map-information":
        from src.client.ui.testing.map_information_surface import build_map_information_surface
        return build_map_information_surface(state, client, context.target_tag)
    if normalized == "map-legend":
        from src.client.visualization.map_modes.empire_mode import EmpireMapMode
        from src.client.visualization.map_modes.gradient_mode import GradientMapMode

        viewport.map_modes = {
            "empire": EmpireMapMode(),
            "gdp_total": GradientMapMode(
                "GDP (Total)", "gdp", use_percentile=True, steps=10,
            ),
        }
        viewport.current_mode_key = str(state.globals.get("ui_map_mode", "gdp_total"))
        viewport.selected_country_tag = "UKR"
        layout = GameLayout(client, context.target_tag, viewport, settings, window)
        return lambda: layout.render(context.selected_region_id, 60.0, navigation, state)
    if normalized == "map-mode-navigation":
        from src.client.visualization.map_modes.gradient_mode import GradientMapMode

        viewport.map_modes = {
            "gdp_total": GradientMapMode(
                "GDP (Total)", "gdp", use_percentile=True, steps=10,
            ),
        }
        viewport.current_mode_key = "political"
        viewport.selected_country_tag = "UKR"
        layout = GameLayout(client, context.target_tag, viewport, settings, window)
        frame = 0

        def draw_map_mode_navigation():
            nonlocal frame
            frame += 1
            if frame == 4:
                layout.show_context_menu(1)
            layout.render(context.selected_region_id, 60.0, navigation, state)

        return draw_map_mode_navigation
    if normalized in {"game-hud", "map-context", "battle-map"}:
        context_unit_ids = set(state.globals.get("ui_context_selected_units", []))
        context_region_id = int(state.globals.get("ui_context_region_id", 1))

        def move_context_units():
            regions = state.tables.get("regions")
            if regions is None or "id" not in regions.columns:
                return
            target = regions.filter(regions["id"] == context_region_id)
            if target.is_empty():
                return
            row = target.row(0, named=True)
            latitude = row.get("latitude", row.get("lat"))
            longitude = row.get("longitude", row.get("lon"))
            if latitude is None or longitude is None:
                return
            layout.unit_move_orders.request(
                context_unit_ids,
                context_region_id,
                float(latitude),
                float(longitude),
            )

        layout = GameLayout(
            client,
            context.target_tag,
            viewport,
            settings,
            window,
            has_selected_units=lambda: bool(context_unit_ids),
            on_move_selected_units=move_context_units,
        )
        if normalized == "battle-map":
            from src.client.controllers.camera_controller import CameraController
            from src.client.renderers.battle_effect_renderer import BattleEffectRenderer
            camera = CameraController()
            camera.look_at_pixel_coords(1024, 512, 2048, 1024)
            battle_renderer = BattleEffectRenderer(camera, 2048, 1024, 1.0)
        frames = 0
        def draw_hud():
            nonlocal frames
            frames += 1
            # The test engine clears pre-existing popups when starting a test.
            if normalized == "map-context" and frames == 4:
                layout.show_context_menu(int(state.globals.get("ui_context_region_id", 1)))
            if normalized == "battle-map":
                from src.client.ui.core.instrumented_imgui import imgui
                from src.client.ui.core.containers import WindowManager
                size = imgui.get_io().display_size
                camera.update_matrices(int(size.x), int(size.y))
                battle_renderer.render(state, reduce_motion=True)
                flags = (imgui.WindowFlags_.no_decoration | imgui.WindowFlags_.no_background
                         | imgui.WindowFlags_.no_bring_to_front_on_focus)
                with WindowManager.window("Battle marker input", w=size.x, h=size.y, flags=flags,
                                          closable=False, test_id="battle.map.fixture"):
                    for marker in battle_renderer.last_layout:
                        imgui.set_cursor_screen_pos((marker.label_x, marker.label_y))
                        if imgui.invisible_button("##" + marker.battle_id,
                                                  (max(44.0, len(marker.label) * 7.0 + 18.0), 22),
                                                  test_id=f"battle.map.marker.{marker.battle_id}"):
                            mouse = imgui.get_mouse_pos()
                            layout.select_battle_at(battle_renderer, mouse.x, size.y - mouse.y, size.y)
            layout.render(context.selected_region_id, 60.0, navigation, state)
        def draw_hud_and_dispatch_navigation():
            draw_hud()
            layout.dispatch_pending_navigation(navigation)

        return draw_hud_and_dispatch_navigation
    if normalized == "editor-hud":
        layout = EditorLayout(client, viewport)
        return lambda: layout.render(60.0)
    if normalized == "unit-context":
        layout = GameLayout(client,context.target_tag,viewport,settings,window)
        targeting = {"mode": None}
        prompt = UnitOrderTargetingPrompt()
        menu = UnitContextMenu(layout.composer,lambda: None,layout.unit_reorganization.open_unit_list,
            on_split=layout.unit_reorganization.open_split,on_merge=layout.unit_reorganization.open_merge,
            on_move_requested=lambda _unit_id: targeting.update(mode="move"),
            on_attack_requested=lambda _unit_id: targeting.update(mode="attack"))
        frames = 0
        def draw_unit_context():
            nonlocal frames
            frames += 1
            if frames == 4:
                menu.show("unit-1")
            layout.render(context.selected_region_id,60.0,navigation,state)
            menu.render()
            prompt.render(targeting["mode"],lambda: targeting.update(mode=None))
        return draw_unit_context
    if normalized == "unit-details":
        panel = UnitDetailsWindow()
        panel.open_for_unit("unit-1")
        return lambda: panel.render(state)
    if normalized == "main-menu":
        from src.client.ui.components.shared.save_game_dialog import SaveGameDialog

        load_game_state = {"open": False}
        save_rows = list((fixture or {}).get("saved_games", []))

        def load_saved_game(save_name: str) -> None:
            navigation.load_saved_game(window.game_config, save_name)
            load_game_state["open"] = False

        load_game_dialog = SaveGameDialog(
            list_saves=lambda: list(save_rows),
            save=lambda _name: None,
            load=load_saved_game,
            notify=lambda *_args, **_kwargs: None,
        )

        def open_load_game() -> None:
            navigation.show_load_game_screen(window.game_config)
            load_game_state["open"] = True
            load_game_dialog.toggle("load")

        menu = MainMenuContent(
            UIComposer(GAMETHEME),
            GameSettingsContent(settings, window, staged=True),
            build_main_menu_actions(lambda: None, open_load_game, lambda: None),
        )

        def draw_main_menu() -> None:
            if load_game_state["open"]:
                load_game_dialog.render()
            else:
                menu.render(*window.get_size())

        return draw_main_menu
    if normalized in {"multiplayer-input-dialog", "multiplayer-server-info"}:
        from src.client.ui.components.shared.multiplayer_windows import (
            GenericInputDialog,
            MultiplayerServerInfo,
            ServerInfoWindow,
        )

        if normalized == "multiplayer-input-dialog":
            dialog = GenericInputDialog()
            dialog.show(
                "PASSWORD",
                lambda value: navigation.requests.append({
                    "type": "multiplayer_password_submitted", "value": value,
                }),
                password=True,
            )
            return lambda: dialog.render(*window.get_size())

        dialog = ServerInfoWindow()
        dialog.show(
            MultiplayerServerInfo(
                "OpenPower Test Lobby", "192.0.2.10", 2, 8,
                "OpenPower", "Test Scenario", password_required=True,
            ),
            on_join=lambda: navigation.requests.append({
                "type": "multiplayer_server_join_requested",
            }),
        )
        return lambda: dialog.render(*window.get_size())
    if normalized == "new-game-selection":
        from types import SimpleNamespace
        from src.client.services.campaign_selection import (
            filter_playable_countries,
            filter_selectable_countries,
        )
        from src.client.ui.components.shared.campaign_scenario_selection_window import CampaignScenarioSelectionWindow
        from src.client.ui.components.shared.country_profile_window import CountryProfileWindow
        from src.client.ui.components.shared.party_selection_window import PartySelectionWindow
        from src.client.ui.components.shared.single_player_setup_window import SinglePlayerSetupWindow
        from src.client.views.new_game_view import NewGameView

        scenarios = state.tables["campaign_scenarios"].to_dicts()
        selected_scenario_id = str(scenarios[0]["id"]) if scenarios else None
        selected_scenario = next(
            (row for row in scenarios if str(row.get("id")) == selected_scenario_id), None
        )
        playable_countries = filter_playable_countries(state.tables["countries"])
        new_game = SimpleNamespace(
            window=window,
            net=client,
            setup_stage="scenario",
            scenario_selection_window=CampaignScenarioSelectionWindow(),
            single_player_setup_window=SinglePlayerSetupWindow(),
            campaign_scenarios=scenarios,
            selected_scenario_id=selected_scenario_id,
            selected_country_id=None,
            selected_party_id="",
            playable_countries=filter_selectable_countries(
                playable_countries, selected_scenario
            ),
            _selected_scenario=lambda: next(
                (
                    row for row in scenarios
                    if str(row.get("id")) == str(new_game.selected_scenario_id)
                ),
                None,
            ),
            _focus_camera_on_country=lambda _tag: None,
            _highlight_country=lambda _tag: None,
        )

        def select_scenario(scenario_id):
            new_game.selected_scenario_id = str(scenario_id)
            new_game.playable_countries = filter_selectable_countries(
                playable_countries, new_game._selected_scenario()
            )
            eligible_ids = {
                str(value).strip().upper()
                for value in new_game.playable_countries["id"].to_list()
            }
            if str(new_game.selected_country_id or "").upper() not in eligible_ids:
                new_game.selected_country_id = None
                new_game.selected_party_id = ""

        def open_profile():
            eligible = (
                new_game.playable_countries["id"].to_list()
                if "id" in new_game.playable_countries.columns else []
            )
            new_game.country_profile_window.show(state, eligible)

        def open_party():
            if new_game.selected_country_id:
                new_game.party_selection_window.show(
                    state,
                    new_game.selected_country_id,
                    new_game.selected_party_id,
                )

        def select_country(country_id):
            new_game.selected_country_id = str(country_id or "").strip().upper() or None
            if not new_game.selected_country_id:
                new_game.selected_party_id = ""
                return
            new_game.selected_party_id = PartySelectionWindow.default_party_id(
                state, new_game.selected_country_id
            )

        new_game._select_scenario = select_scenario
        new_game._select_country = select_country
        new_game._enter_country_setup = lambda: setattr(new_game, "setup_stage", "country")
        new_game._return_to_scenario_selection = lambda: setattr(new_game, "setup_stage", "scenario")
        new_game._return_to_main_menu = lambda: None
        new_game._open_country_profile = lambda _state: open_profile()
        new_game._open_party_selection = lambda _state: open_party()
        new_game._start_game = lambda: None
        new_game.country_profile_window = CountryProfileWindow(select_country)
        new_game.party_selection_window = PartySelectionWindow(
            lambda party_id: setattr(new_game, "selected_party_id", party_id)
        )
        return lambda: NewGameView._render_ui(new_game)
    manager, specs = panel_specs(settings, window)
    for spec in specs:
        manager.register_spec(spec)
    selected = next((s for s in specs if s.id.lower().replace("_", "-") == normalized), None)
    if selected is None:
        raise ValueError(f"Unknown UI surface: {name}. Use 'openpower ui-test list'.")
    manager.set_visible(selected.id, True)
    return lambda: manager.render_all(state, context)
