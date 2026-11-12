from typing import Optional

import arcade
import polars as pl
from src.client.ui.core.instrumented_imgui import imgui

from src.client.services.network_client_service import NetworkClient
from src.client.ui.components.hud.central_bar import CentralBar
from src.client.ui.components.hud.country_selector import resolve_country_status
from src.client.ui.components.hud.context_menu import ContextMenu
from src.client.ui.components.hud.thematic_map_legend import ThematicMapLegend
from src.client.ui.components.hud.system_bar import SystemBar
from src.client.ui.components.hud.toggle_bar import ToggleBar
from src.client.ui.components.hud.mini_map import MiniMapPanel
from src.client.ui.components.main_menu_content import MainMenuContent, build_in_game_menu_actions
from src.client.ui.components.guided_tutorial_window import GuidedTutorialWindow
from src.client.ui.components.settings_content import GameSettingsContent
from src.client.ui.components.hud.panel_shortcuts import consume_panel_shortcuts
from src.client.ui.components.hud.panel_manager import PanelManager, PanelSpec
from src.client.ui.panels.service.performance_panel import PerformancePanel
from imgui_bundle import icons_fontawesome_6
from src.client.ui.core.composer import UIComposer
from src.client.ui.core.containers import WindowManager
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.core.theme import GAMETHEME
from src.client.ui.components.shared.dirty_close_confirmation import SaveConfirmationPreferences
from src.client.ui.components.shared.generic_message_dialog import GenericMessageDialog
from src.client.ui.components.shared.generic_question_dialog import GenericQuestionDialog
from src.client.ui.components.shared.command_feedback import CommandFeedback
from src.client.ui.components.shared.unit_order_feedback import UnitOrderFeedback
from src.client.ui.components.shared.save_game_dialog import SaveGameDialog
from src.client.ui.components.shared.battle_summary_dialog import BattleSummaryDialog
from src.client.ui.components.shared.advisor_recommendation_window import AdvisorRecommendationWindow
from src.client.ui.components.shared.game_over_dialog import GameOverDialog
from src.core.saves import list_available_saves
from src.shared.actions import ActionSaveGame
from src.client.services.autosave_scheduler import AutosaveScheduler
from src.client.ui.layouts.game_panel_registry import build_game_panel_specs
from src.client.ui.panels.service.feed_presenter import FeedPresenter
from src.client.ui.panels.service.mail_inbox_state import MailInboxState
from src.client.ui.panels.military.unit_reorganization_windows import UnitReorganizationWindows
from src.client.ui.components.shared.covert_outcome_dialog import CovertOutcomeDialog
from src.client.ui.components.shared.text_notification_dialog import TextNotificationDialog
from src.client.ui.panels.service.treaty_refusal_report import treaty_refusal_report
from src.client.ui.panels.military.battle_inspection_windows import BattleInspectionWindows
from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.client.controllers.unit_move_orders import UnitMoveOrders
from src.client.ui.panels.military.unit_attack_confirmation import UnitAttackConfirmation


class GameLayout:
    """Composition root for the Game HUD."""

    def __init__(
        self,
        net_client: NetworkClient,
        player_tag: str,
        viewport_ctrl,
        settings_service=None,
        window=None,
        has_selected_units=None,
        on_move_selected_units=None,
        on_deployment_drag_start=None,
    ):
        self.net = net_client
        self.autosave = AutosaveScheduler(settings_service, net_client)
        self.local_player_tag = player_tag
        self.viewport_ctrl = viewport_ctrl
        self._on_deployment_drag_start = on_deployment_drag_start
        self.save_confirmation_preferences = SaveConfirmationPreferences()
        self.message_dialog = GenericMessageDialog()
        self.advisor_question_dialog = GenericQuestionDialog("advisor.recommendation.question")
        self.advisor_recommendation_window = AdvisorRecommendationWindow(net_client, self.local_player_tag)
        initial_state = self.net.get_state()
        self.command_feedback = CommandFeedback(
            self.message_dialog,
            getattr(getattr(initial_state, "journal", None), "command_results", []),
        )
        self.unit_order_feedback = UnitOrderFeedback(
            self.message_dialog,
            initial_state.tables.get("unit_order_feedback"),
        )
        self._window = window
        self._navigation = None
        self._stop_game_requested = False
        self.battle_summary_dialog = BattleSummaryDialog()
        self.game_over_dialog = GameOverDialog()
        self.covert_outcome_dialog = CovertOutcomeDialog()
        self.dispatch_report_dialog = TextNotificationDialog()
        self.battle_inspection = BattleInspectionWindows(self.net, self.local_player_tag)
        self.unit_reorganization = UnitReorganizationWindows(self.net,self.local_player_tag,self.message_dialog.enqueue)
        self.unit_move_orders = UnitMoveOrders(self.net, self.local_player_tag, self.message_dialog.enqueue)
        self.unit_attack_confirmation = UnitAttackConfirmation(self.unit_move_orders)
        self.save_game_dialog = SaveGameDialog(
            self._list_saves,
            lambda name: self.net.send_action(ActionSaveGame(self.net.player_id, name)),
            self._load_save,
            self.message_dialog.enqueue,
        )

        self.composer = UIComposer(GAMETHEME)
        self.panel_manager = PanelManager()
        self.tutorial_window = GuidedTutorialWindow()
        self._game_menu_visible = False
        self.game_menu = MainMenuContent(
            self.composer,
            GameSettingsContent(settings_service, window, staged=True),
            build_in_game_menu_actions(
                self._close_game_menu,
                self._request_window_close
                if callable(getattr(window, "close", None))
                else None,
                self._request_stop_game,
            ),
            test_id_prefix="game_menu",
            in_game=True,
        )
        self.mail_inbox_state = MailInboxState()
        for spec in build_game_panel_specs(self.panel_manager, settings_service, window,
                                           open_dispatch_cb=self._open_dispatch,
                                           open_unit_train_cb=self.unit_reorganization.open_training,
                                           open_battle_cb=lambda battle_id: self.battle_inspection.open(self.net.get_state(), battle_id),
                                           mail_inbox_state=self.mail_inbox_state,
                                           open_tutorial_cb=self._open_tutorial,
                                           close_mail_cb=lambda: self.panel_manager.set_visible("MAIL", False)):
            self.panel_manager.register_spec(spec)

        telemetry = getattr(getattr(self.net, "session", None), "telemetry", None)
        if telemetry is not None:
            self.panel_manager.register_spec(PanelSpec(
                id="PERFORMANCE", title="Performance Monitor", category="service",
                factory=lambda: PerformancePanel(telemetry),
                icon=icons_fontawesome_6.ICON_FA_CHART_LINE,
            ))

        self.feed_presenter = FeedPresenter(self.mail_inbox_state)
        self.toggle_bar = ToggleBar(self.panel_manager)
        self.mini_map = MiniMapPanel(
            self.viewport_ctrl, self.local_player_tag, self.tutorial_window.on_interaction,
        )
        self.central_bar = CentralBar(
            open_ai_cb=lambda: self.panel_manager.toggle("ADVISOR_SETTINGS"),
            open_statistics_cb=lambda: self.panel_manager.toggle("HISTORY"),
            open_mail_cb=lambda: self.panel_manager.toggle("MAIL"),
            open_news_cb=lambda: self.panel_manager.toggle("NEWS_LOG"),
            open_relations_cb=lambda: self.panel_manager.set_visible("RELATIONS", True),
            open_more_info_cb=lambda: self.panel_manager.set_visible("COUNTRY_MORE_INFO", True),
            panel_visible_cb=self.panel_manager.is_visible,
            open_locate_cb=self._on_focus_region,
            focus_country_cb=self._on_focus_country,
        )
        self.system_bar = SystemBar(
            open_help_cb=lambda: self.panel_manager.set_visible("TOOLTIP_HELP", True),
            open_objectives_cb=lambda: self.panel_manager.toggle("OBJECTIVES"),
            open_console_cb=lambda: self.panel_manager.toggle("CONSOLE"),
            open_history_cb=lambda: self.panel_manager.set_visible("HISTORY", True),
            open_menu_cb=self._toggle_game_menu,
            open_save_cb=lambda: self.save_game_dialog.toggle("save"),
            open_load_cb=lambda: self.save_game_dialog.toggle("load"),
        )
        self.context_menu = ContextMenu(
            self.composer,
            self.panel_manager,
            self.viewport_ctrl,
            has_selected_units=has_selected_units,
            on_move_selected_units=on_move_selected_units,
            on_quick_treaty=self._open_quick_treaty,
        )
        self.thematic_map_legend = ThematicMapLegend(
            self.viewport_ctrl,
            flag_renderer=self.central_bar.flag_renderer,
        )

        self._last_selected_id: Optional[int] = None
        self._cached_target_tag: str = player_tag

    def render(
        self,
        selected_region_id: Optional[int],
        fps: float,
        nav_service,
        state=None,
        presentation_total_minutes: float | None = None,
    ):
        GAMETHEME.apply()
        WindowManager.begin_frame()
        self._navigation = nav_service
        if state is None:
            state = self.net.get_state()

        target_tag, is_own = self._resolve_active_context(state, selected_region_id)
        hud_summary = self.feed_presenter.build_summary(state, target_tag)
        country_status = resolve_country_status(state, self.local_player_tag, target_tag)
        command_results = getattr(getattr(state, "journal", None), "command_results", [])
        quiet_save_results = self.autosave.update(
            command_results,
            game_over=self.game_over_dialog.is_game_over(state, self.local_player_tag),
        )
        self.command_feedback.update(command_results, self.net.player_id, quiet_save_results)
        self.unit_order_feedback.update(
            state.tables.get("unit_order_feedback"), self.local_player_tag,
        )
        self.system_bar.render(self.net, nav_service, hud_summary)

        req_tag = self.central_bar.render(
            state,
            self.net,
            target_tag,
            country_status,
            hud_summary,
        )
        if req_tag:
            self._cached_target_tag = req_tag
            target_tag = req_tag
            is_own = req_tag == self.local_player_tag
            hud_summary = self.feed_presenter.build_summary(state, target_tag)
            if hasattr(self.viewport_ctrl, "focus_on_country"):
                focused_region_id = self.viewport_ctrl.focus_on_country(req_tag)
                if focused_region_id is not None:
                    selected_region_id = focused_region_id

        self.toggle_bar.render()
        self.mini_map.render()
        consume_panel_shortcuts(self.panel_manager)

        context = PanelRenderContext(
            target_tag=target_tag,
            is_own_country=is_own,
            player_country_tag=self.local_player_tag,
            selected_region_id=selected_region_id,
            on_focus_request=self._on_focus_region,
            net_client=self.net,
            presentation_total_minutes=presentation_total_minutes,
            on_deployment_drag_start=self._on_deployment_drag_start,
            save_confirmation_preferences=self.save_confirmation_preferences,
            on_notice=self.message_dialog.enqueue,
            on_question=self.advisor_question_dialog.show,
            on_advisor_recommendation=self.advisor_recommendation_window.open,
        )
        self.panel_manager.render_all(state, context)
        self.tutorial_window.render(self.panel_manager.is_visible)
        self.context_menu.render(state, self.local_player_tag)
        self.thematic_map_legend.render(state, self.local_player_tag)
        self.save_game_dialog.render()
        self.battle_summary_dialog.render(state)
        self.unit_reorganization.render(state)
        self.covert_outcome_dialog.render(state)
        self.dispatch_report_dialog.render()
        self.battle_inspection.render(state)
        self.unit_attack_confirmation.render(state)
        self.advisor_recommendation_window.render(state)

        # Render system errors warning banner if any are collected
        errors = self.net.get_system_errors()
        if errors:
            self._render_system_errors_banner(errors)
        self.message_dialog.render()
        self.advisor_question_dialog.render()

        self._render_fps(fps)
        self._render_game_menu()
        self.game_over_dialog.render(
            state,
            self.local_player_tag,
            on_return_to_menu=self._request_stop_game,
        )

    def show_context_menu(self, region_id: int):
        self.context_menu.show(region_id)

    def _toggle_game_menu(self) -> None:
        self._game_menu_visible = not self._game_menu_visible

    def _open_tutorial(self, guide_id: str) -> None:
        self.panel_manager.set_visible("TOOLTIP_HELP", False)
        self.tutorial_window.open(guide_id)

    def _close_game_menu(self) -> None:
        self._game_menu_visible = False

    def _request_stop_game(self) -> None:
        self._game_menu_visible = False
        self._stop_game_requested = True

    def dispatch_pending_navigation(self, nav_service=None) -> bool:
        if not self._stop_game_requested:
            return False
        self._stop_game_requested = False
        navigation = nav_service or self._navigation
        stop_game = getattr(navigation, "stop_game", None)
        if not callable(stop_game):
            return False
        stop_game()
        return True

    def _request_window_close(self) -> None:
        window = self._window
        if window is None:
            return

        # The Exit button runs during ImGui drawing, so wait for this frame to present before destroying its GL context.
        arcade.schedule_once(lambda _delta_time: window.close(), 1 / 60)

    def _render_game_menu(self) -> None:
        if not self._game_menu_visible:
            return
        viewport = imgui.get_main_viewport()
        self.game_menu.render(float(viewport.size.x), float(viewport.size.y))

    def _list_saves(self):
        config = getattr(self._window, "game_config", None)
        return list_available_saves(config) if config is not None else []

    def select_battle_at(self, renderer, x, y, viewport_height) -> bool:
        battle_id = renderer.battle_at(x, y, viewport_height)
        return bool(battle_id and self.battle_inspection.open(self.net.get_state(), battle_id))

    def _open_dispatch(self, dispatch):
        self._cached_target_tag = self.local_player_tag
        if dispatch["kind"] == "battle":
            payload = dispatch["payload"]
            losses = MilitaryPresenter().battle_loss_summary(
                self.net.get_state(), str(payload.get("battle_id") or ""), self.local_player_tag,
            )
            self.battle_summary_dialog.show(payload, losses=losses)
        elif dispatch["kind"] == "covert":
            self.covert_outcome_dialog.show(dispatch["reference"],self.local_player_tag)
        elif dispatch["kind"] == "covert_ready":
            for entry in self.panel_manager.get_entries():
                if entry.id == "COVERT_OPS":
                    entry.instance.request_cell(dispatch["reference"], dispatch["payload"].get("mission_id", ""))
                    self.panel_manager.set_visible(entry.id, True)
        elif dispatch["kind"] == "treaty_refusal":
            self.dispatch_report_dialog.enqueue(treaty_refusal_report(self.net.get_state(), dispatch["payload"]))
        elif dispatch["kind"] == "region_control":
            self.dispatch_report_dialog.enqueue(str(dispatch.get("body") or ""))
        elif dispatch["kind"] == "treaty":
            for entry in self.panel_manager.get_entries():
                if entry.id == "TREATIES":
                    entry.instance.request_treaty(dispatch["reference"])
                    self.panel_manager.set_visible(entry.id, True)
        elif dispatch["kind"] == "trade":
            for entry in self.panel_manager.get_entries():
                if entry.id == "TRADE":
                    entry.instance.request_deal(dispatch["reference"])
                    self.panel_manager.set_visible(entry.id, True)

    def _load_save(self, name):
        config = getattr(self._window, "game_config", None)
        if config is not None and self._navigation is not None:
            self._navigation.load_saved_game(config, name)
        else:
            self.message_dialog.enqueue("Load game", "No active game configuration.", severity="error")

    def _open_quick_treaty(self, target_tag, treaty_type, invert_sides=False):
        for entry in self.panel_manager.get_entries():
            if entry.id == "NEW_TREATY":
                entry.instance.prepare(self.local_player_tag, target_tag, treaty_type,
                                       invert_sides=invert_sides)
                self.panel_manager.set_visible(entry.id, True)
                return

    def _on_focus_region(self, region_id):
        self.viewport_ctrl.focus_on_region(region_id)

    def _on_focus_country(self, country_tag):
        self.viewport_ctrl.focus_on_country(country_tag)

    def _render_fps(self, fps: float):
        imgui.set_next_window_pos((10, 10))
        flags = (
            imgui.WindowFlags_.no_decoration
            | imgui.WindowFlags_.no_inputs
            | imgui.WindowFlags_.no_background
            | imgui.WindowFlags_.always_auto_resize
        )

        if imgui.begin("##FPS", True, flags):
            imgui.text_colored((1, 1, 1, 1), f"{fps:.0f}")
        imgui.end()

    def _render_system_errors_banner(self, errors: list):
        imgui.set_next_window_pos((imgui.get_io().display_size.x * 0.5 - 250, 40))
        imgui.set_next_window_size((500, 0))
        flags = (
            imgui.WindowFlags_.no_collapse
            | imgui.WindowFlags_.always_auto_resize
        )
        imgui.push_style_color(imgui.Col_.window_bg, (0.6, 0.1, 0.1, 0.95))
        imgui.push_style_color(imgui.Col_.title_bg, (0.8, 0.1, 0.1, 1.0))
        imgui.push_style_color(imgui.Col_.title_bg_active, (0.9, 0.1, 0.1, 1.0))
        
        if imgui.begin("SIMULATION ERRORS DETECTED", True, flags):
            imgui.text_wrapped("One or more simulation systems crashed! Check console logs for full tracebacks.")
            imgui.separator()
            for err in errors[-2:]:
                imgui.text_colored((1, 1, 0, 1), f"[{err['system_id']}] {err['message']}")
            imgui.separator()
            if imgui.button("Details", test_id="system_errors.details"):
                details = "\n\n".join(
                    f"[{err['system_id']}] {err['message']}"
                    for err in errors[-8:]
                )
                self.message_dialog.enqueue(
                    "Simulation errors",
                    details,
                    severity="error",
                )
                imgui.set_next_window_focus()
            imgui.same_line()
            if imgui.button("Clear errors"):
                self.net.clear_system_errors()
        imgui.end()
        
        imgui.pop_style_color(3)

    def _resolve_active_context(self, state, region_id: Optional[int]) -> tuple[str, bool]:
        if region_id != self._last_selected_id:
            self._last_selected_id = region_id
            if not region_id:
                self._cached_target_tag = self.local_player_tag
            elif "regions" in state.tables:
                try:
                    region_rows = state.tables["regions"].filter(pl.col("id") == region_id)
                    if region_rows.is_empty():
                        self._cached_target_tag = self.local_player_tag
                    else:
                        region_row = region_rows.row(0, named=True)
                        authority = region_row.get("controller") or region_row.get("owner")
                        self._cached_target_tag = authority if authority and authority != "None" else self.local_player_tag
                except Exception:
                    self._cached_target_tag = self.local_player_tag

        return self._cached_target_tag, self._cached_target_tag == self.local_player_tag

