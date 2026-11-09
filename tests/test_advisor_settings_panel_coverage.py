from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl
import pytest

from src.client.ui.components.shared.dirty_close_confirmation import CloseDecision
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.service import advisor_settings_panel as panel_module
from src.client.ui.panels.service.advisor_settings_panel import AdvisorSettingsPanel
from src.shared.advisor_settings import ADVISOR_STATUS_COLUMNS, preferences_from_modes


DEFAULT_MODES = {"economy": "manual", "politics": "automatic", "military": "confirmations"}


def state_with_modes(modes=DEFAULT_MODES, *, country_ids=("UKR",), results=()):
    rows = []
    for country_id in country_ids:
        rows.append(
            {
                "id": country_id,
                **{
                    ADVISOR_STATUS_COLUMNS[domain]: modes[domain]
                    for domain in ADVISOR_STATUS_COLUMNS
                },
            }
        )
    return SimpleNamespace(
        globals={},
        tables={"countries": pl.DataFrame(rows)},
        journal=SimpleNamespace(command_results=list(results)),
    )


def context(*, country="UKR", client=None, preferences=None, is_own=True, target="UKR"):
    return PanelRenderContext(
        target_tag=target,
        is_own_country=is_own,
        net_client=client,
        save_confirmation_preferences=preferences,
        player_country_tag=country,
    )


@pytest.mark.parametrize(
    ("render_context", "state_globals", "expected"),
    [
        (context(country=" gbr "), {"player_tag": "FRA"}, "GBR"),
        (context(country=""), {"player_tag": " fra "}, "FRA"),
        (context(country="", is_own=True, target=" usa "), {}, "USA"),
        (context(country="", is_own=False, target="USA"), {}, ""),
    ],
)
def test_player_country_tag_uses_context_then_state_then_owned_target(
    render_context, state_globals, expected
):
    assert AdvisorSettingsPanel._player_country_tag(
        SimpleNamespace(globals=state_globals), render_context
    ) == expected


@pytest.mark.parametrize(
    ("countries", "country", "expected"),
    [
        (
            pl.DataFrame(
                {
                    "id": [" ukr "],
                    "advisor_economy_status": [" AUTOMATIC "],
                    "advisor_politics_status": ["manual"],
                    "advisor_military_status": ["confirmations"],
                }
            ),
            "UKR",
            {"economy": "automatic", "politics": "manual", "military": "confirmations"},
        ),
        (None, "UKR", None),
        (pl.DataFrame({"id": ["UKR"]}), "UKR", None),
        (
            pl.DataFrame(
                {
                    "id": ["UKR", "UKR"],
                    "advisor_economy_status": ["manual", "manual"],
                    "advisor_politics_status": ["manual", "manual"],
                    "advisor_military_status": ["manual", "manual"],
                }
            ),
            "UKR",
            None,
        ),
        (
            pl.DataFrame(
                {
                    "id": ["UKR"],
                    "advisor_economy_status": ["unknown"],
                    "advisor_politics_status": ["manual"],
                    "advisor_military_status": ["manual"],
                }
            ),
            "UKR",
            None,
        ),
        (pl.DataFrame({"id": ["UKR"]}), "", None),
    ],
)
def test_read_authoritative_modes_validates_country_and_modes(countries, country, expected):
    state = SimpleNamespace(tables={"countries": countries} if countries is not None else {})
    assert AdvisorSettingsPanel._read_authoritative_modes(state, country) == expected


def test_sync_from_state_preserves_dirty_and_pending_drafts():
    panel = AdvisorSettingsPanel()
    original = {"advisor_economy_manual": False}
    panel._draft = original.copy()
    panel._dirty = True
    panel._sync_from_state(state_with_modes(), "UKR")
    assert panel._draft == original

    panel._dirty = False
    panel._pending_modes = DEFAULT_MODES.copy()
    panel._sync_from_state(state_with_modes(), "UKR")
    assert panel._draft == original


def test_sync_from_state_uses_authoritative_modes_then_local_fallback():
    panel = AdvisorSettingsPanel()
    panel._sync_from_state(state_with_modes(), "UKR")
    assert panel._draft == preferences_from_modes(DEFAULT_MODES)

    settings = SimpleNamespace(
        advisor_economy_manual=0,
        advisor_economy_automatic=1,
        advisor_politics_confirmations=0,
    )
    panel._settings_service = SimpleNamespace(settings=settings)
    panel._sync_from_state(SimpleNamespace(tables={}), "UKR")
    assert panel._draft["advisor_economy_manual"] is False
    assert panel._draft["advisor_economy_automatic"] is True
    assert panel._draft["advisor_economy_confirmations"] is True
    assert panel._draft["advisor_politics_confirmations"] is False
    assert panel._draft["advisor_military_automatic"] is False


def test_sync_from_local_settings_supplies_defaults_without_service():
    panel = AdvisorSettingsPanel()
    panel._sync_from_local_settings()
    assert len(panel._draft) == 9
    assert all(panel._draft[f"advisor_{domain}_manual"] for domain in panel._DOMAINS)
    assert all(not panel._draft[f"advisor_{domain}_automatic"] for domain in panel._DOMAINS)
    assert all(panel._draft[f"advisor_{domain}_confirmations"] for domain in panel._DOMAINS)


def test_reconcile_pending_returns_when_no_action_is_pending():
    panel = AdvisorSettingsPanel()
    panel._reconcile_pending(state_with_modes(), "UKR")
    assert panel._pending_modes is None


@pytest.mark.parametrize(
    "result",
    [
        {"action_type": "OtherAction", "player_id": "player", "status": "rejected"},
        {
            "action_type": "ActionUpdateAdvisorSettings",
            "player_id": "other",
            "status": "rejected",
        },
        {
            "action_type": "ActionUpdateAdvisorSettings",
            "player_id": "player",
            "country_id": "FRA",
            "status": "rejected",
        },
        {
            "action_type": "ActionUpdateAdvisorSettings",
            "player_id": "player",
            "country_id": "",
            "status": "accepted",
        },
    ],
)
def test_reconcile_pending_ignores_unrelated_or_successful_results(result):
    panel = AdvisorSettingsPanel()
    panel._pending_modes = {"economy": "automatic", "politics": "manual", "military": "manual"}
    panel._pending_player_id = "player"
    panel._pending_country = "UKR"
    panel._pending_result_cursor = 0

    panel._reconcile_pending(state_with_modes(results=[result]), "UKR")

    assert panel._pending_modes is not None
    assert not panel._dirty


@pytest.mark.parametrize("status", ["REJECTED", "Failed"])
def test_reconcile_pending_rejection_restores_dirty_editable_state(status):
    panel = AdvisorSettingsPanel()
    panel._pending_modes = {"economy": "automatic", "politics": "manual", "military": "manual"}
    panel._pending_player_id = "player"
    panel._pending_country = "UKR"
    panel._pending_result_cursor = 1
    results = [
        {"action_type": "ActionUpdateAdvisorSettings", "player_id": "player", "status": "failed"},
        {
            "action_type": "ActionUpdateAdvisorSettings",
            "actor_id": "player",
            "country_id": " ukr ",
            "status": status,
        },
    ]

    panel._reconcile_pending(state_with_modes(results=results), "UKR")

    assert panel._pending_modes is None
    assert panel._dirty


def test_reconcile_pending_waits_until_authoritative_modes_match():
    panel = AdvisorSettingsPanel()
    panel._pending_modes = {"economy": "automatic", "politics": "manual", "military": "manual"}
    panel._pending_country = "UKR"
    panel._pending_result_cursor = 0
    panel._dirty = True
    panel._reconcile_pending(state_with_modes(), "UKR")
    assert panel._pending_modes is not None
    assert panel._dirty


def test_reconcile_pending_commits_matching_authoritative_modes_to_preferences():
    settings_service = SimpleNamespace(set_advisor_preferences=Mock())
    panel = AdvisorSettingsPanel(settings_service)
    panel._pending_modes = DEFAULT_MODES.copy()
    panel._pending_country = "UKR"
    panel._pending_result_cursor = 0
    panel._dirty = True

    panel._reconcile_pending(state_with_modes(), "UKR")

    assert panel._pending_modes is None
    assert panel._draft == preferences_from_modes(DEFAULT_MODES)
    assert not panel._dirty
    settings_service.set_advisor_preferences.assert_called_once_with(panel._draft)


def test_render_preferences_draws_all_toggles_and_tracks_changes(monkeypatch):
    panel = AdvisorSettingsPanel()
    panel._draft = {f"advisor_{domain}_{option}": False for domain in panel._DOMAINS for option in panel._OPTIONS}
    widget = SimpleNamespace(text_at=Mock())
    monkeypatch.setattr(panel_module, "GMLWidgets", lambda _: widget)
    changed_key = "advisor_economy_manual"
    imgui_stub = SimpleNamespace(
        text_disabled=Mock(),
        invisible_button=Mock(side_effect=lambda label, *args, **kwargs: label == f"##{changed_key}"),
        is_item_hovered=Mock(return_value=True),
        set_tooltip=Mock(),
    )
    monkeypatch.setattr(panel_module, "imgui", imgui_stub)
    drawn = []
    monkeypatch.setattr(panel, "_draw_toggle", drawn.append)

    panel._render_preferences()

    assert panel._dirty
    assert panel._draft[changed_key]
    assert len(drawn) == 9
    assert imgui_stub.text_disabled.call_count == 3
    assert imgui_stub.invisible_button.call_count == 9
    assert imgui_stub.set_tooltip.call_count == 6
    assert widget.text_at.call_count == 3


@pytest.mark.parametrize("checked", [True, False])
@pytest.mark.parametrize("hovered", [True, False])
def test_draw_toggle_uses_state_and_hover_colors(monkeypatch, checked, hovered):
    minimum, maximum = object(), object()
    draw_list = SimpleNamespace(add_rect_filled=Mock(), add_rect=Mock())
    colors = SimpleNamespace(
        interaction_active="active",
        bg_input="input",
        accent="accent",
        text_dim="dim",
    )
    imgui_stub = SimpleNamespace(
        get_item_rect_min=Mock(return_value=minimum),
        get_item_rect_max=Mock(return_value=maximum),
        get_window_draw_list=Mock(return_value=draw_list),
        is_item_hovered=Mock(return_value=hovered),
        get_color_u32=Mock(side_effect=lambda color: f"encoded:{color}"),
    )
    monkeypatch.setattr(panel_module, "GAMETHEME", SimpleNamespace(colors=colors))
    monkeypatch.setattr(panel_module, "imgui", imgui_stub)

    AdvisorSettingsPanel._draw_toggle(checked)

    draw_list.add_rect_filled.assert_called_once_with(
        minimum, maximum, f"encoded:{'active' if checked else 'input'}"
    )
    draw_list.add_rect.assert_called_once_with(
        minimum, maximum, f"encoded:{'accent' if hovered else 'dim'}", thickness=1.0
    )


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (0, ("togPoliManual", "togMiliManual", "togEconManual")),
        (1, ("togPoliAutomatic", "togMiliAutomatic", "togEconAutomatic")),
        (
            2,
            ("togPoliConfirmations", "togMiliConfirmations", "togEconConfirmations"),
        ),
    ],
)
def test_domain_components_selects_each_option_row(row, expected):
    assert AdvisorSettingsPanel()._domain_components(row) == expected


@pytest.mark.parametrize(
    ("client", "country", "with_service"),
    [(None, "UKR", True), (None, "", False), (SimpleNamespace(), "", True)],
)
def test_apply_without_network_client_saves_local_preferences(client, country, with_service):
    service = SimpleNamespace(set_advisor_preferences=Mock()) if with_service else None
    panel = AdvisorSettingsPanel(service)
    panel._dirty = True
    panel._draft = preferences_from_modes(DEFAULT_MODES)

    panel._apply(state_with_modes(), context(client=client), country)

    assert not panel._dirty
    assert panel._pending_modes is None
    if service is not None:
        service.set_advisor_preferences.assert_called_once_with(panel._draft)


def test_apply_sends_authoritative_modes_and_tracks_pending_result_cursor():
    actions = []
    client = SimpleNamespace(player_id="player-1", send_action=actions.append)
    panel = AdvisorSettingsPanel()
    panel._dirty = True
    panel._draft = preferences_from_modes(DEFAULT_MODES)
    state = state_with_modes(results=[{"status": "old"}, {"status": "old"}])

    panel._apply(state, context(client=client), "UKR")

    assert len(actions) == 1
    assert actions[0].player_id == "player-1"
    assert actions[0].country_tag == "UKR"
    assert actions[0].economy_status == "manual"
    assert actions[0].politics_status == "automatic"
    assert actions[0].military_status == "confirmations"
    assert panel._pending_result_cursor == 2
    assert panel._pending_player_id == "player-1"
    assert panel._pending_country == "UKR"
    assert panel._pending_modes == DEFAULT_MODES


def test_finish_close_applies_or_discards_then_syncs_state(monkeypatch):
    panel = AdvisorSettingsPanel()
    panel._dirty = True
    apply = Mock()
    sync = Mock()
    monkeypatch.setattr(panel, "_apply", apply)
    monkeypatch.setattr(panel, "_sync_from_state", sync)
    state = object()
    render_context = context()

    panel._finish_close(CloseDecision.APPLY, state, render_context, "UKR")
    apply.assert_called_once_with(state, render_context, "UKR")
    sync.assert_called_once_with(state, "UKR")
    assert panel._dirty

    panel._dirty = True
    panel._finish_close(CloseDecision.DISCARD, state, render_context, "UKR")
    assert not panel._dirty
    assert apply.call_count == 1
    assert sync.call_count == 2


def install_render_stubs(monkeypatch, *, is_open=True):
    @contextmanager
    def window(*args, **kwargs):
        yield is_open

    monkeypatch.setattr(panel_module.WindowManager, "window", window)
    monkeypatch.setattr(
        panel_module,
        "imgui",
        SimpleNamespace(begin_disabled=Mock(), end_disabled=Mock()),
    )


def test_render_returns_false_for_closed_clean_panel(monkeypatch):
    panel = AdvisorSettingsPanel()
    install_render_stubs(monkeypatch, is_open=False)
    confirmation_render = Mock()
    monkeypatch.setattr(panel._close_confirmation, "render", confirmation_render)

    assert not panel.render(state_with_modes(), context())
    confirmation_render.assert_not_called()


def test_render_keeps_open_panel_and_renders_preferences(monkeypatch):
    panel = AdvisorSettingsPanel()
    install_render_stubs(monkeypatch)
    render_preferences = Mock()
    render_apply = Mock()
    monkeypatch.setattr(panel, "_render_preferences", render_preferences)
    monkeypatch.setattr(panel, "_render_apply_button", render_apply)

    assert panel.render(state_with_modes(), context())
    render_preferences.assert_called_once_with()
    render_apply.assert_called_once()


def test_render_navigation_close_finishes_immediate_remembered_decision(monkeypatch):
    preferences = Mock()
    panel = AdvisorSettingsPanel()
    panel._dirty = True
    panel.request_close()
    install_render_stubs(monkeypatch)
    monkeypatch.setattr(panel._close_confirmation, "request_close", Mock(return_value=CloseDecision.APPLY))
    finish = Mock()
    monkeypatch.setattr(panel, "_finish_close", finish)

    assert not panel.render(state_with_modes(), context(preferences=preferences))
    panel._close_confirmation.request_close.assert_called_once_with(preferences, can_apply=True)
    finish.assert_called_once()


def test_render_confirmation_decision_finishes_after_window_contents(monkeypatch):
    panel = AdvisorSettingsPanel()
    panel._dirty = True
    install_render_stubs(monkeypatch)
    monkeypatch.setattr(panel, "_render_preferences", Mock())
    monkeypatch.setattr(panel, "_render_apply_button", Mock())
    monkeypatch.setattr(
        panel._close_confirmation,
        "render",
        Mock(return_value=CloseDecision.DISCARD),
    )
    finish = Mock()
    monkeypatch.setattr(panel, "_finish_close", finish)

    assert not panel.render(state_with_modes(), context())
    finish.assert_called_once()


def test_render_waits_when_close_confirmation_is_pending_but_apply_is_unavailable(monkeypatch):
    panel = AdvisorSettingsPanel()
    panel._dirty = True
    panel._pending_modes = {
        "economy": "automatic",
        "politics": "manual",
        "military": "manual",
    }
    panel.request_close()
    install_render_stubs(monkeypatch)
    request_close = Mock(return_value=None)
    render_confirmation = Mock(return_value=None)
    monkeypatch.setattr(panel._close_confirmation, "request_close", request_close)
    monkeypatch.setattr(panel._close_confirmation, "render", render_confirmation)

    assert panel.render(state_with_modes(), context())
    request_close.assert_called_once_with(panel._local_preferences, can_apply=False)
    render_confirmation.assert_called_once_with(panel._local_preferences, can_apply=False)


@pytest.mark.parametrize("pending", [False, True])
def test_render_apply_button_tracks_enabled_state_and_pending_tooltip(monkeypatch, pending):
    panel = AdvisorSettingsPanel()
    panel._dirty = not pending
    panel._pending_modes = DEFAULT_MODES.copy() if pending else None
    resumed = []
    monkeypatch.setattr(
        "src.client.ui.layouts.gml_layout.suspend_gml_layout", lambda: "layout-token"
    )
    monkeypatch.setattr(
        "src.client.ui.layouts.gml_layout.resume_gml_layout", resumed.append
    )
    button = Mock(return_value=not pending)
    set_tooltip = Mock()
    imgui_stub = SimpleNamespace(
        get_window_pos=Mock(return_value=SimpleNamespace(x=10.0, y=20.0)),
        set_cursor_screen_pos=Mock(),
        begin_disabled=Mock(),
        end_disabled=Mock(),
        button=button,
        HoveredFlags_=SimpleNamespace(allow_when_disabled=7),
        is_item_hovered=Mock(return_value=pending),
        set_tooltip=set_tooltip,
    )
    monkeypatch.setattr(panel_module, "imgui", imgui_stub)
    apply = Mock()
    monkeypatch.setattr(panel, "_apply", apply)

    panel._render_apply_button(state_with_modes(), context(), "UKR")

    assert resumed == ["layout-token"]
    imgui_stub.set_cursor_screen_pos.assert_called_once_with((250.0, 51.0))
    assert imgui_stub.begin_disabled.call_args.args == (pending,)
    assert apply.call_count == int(not pending)
    if pending:
        set_tooltip.assert_called_once()
    else:
        set_tooltip.assert_not_called()


def test_render_apply_button_resumes_layout_if_drawing_raises(monkeypatch):
    panel = AdvisorSettingsPanel()
    panel._dirty = True
    resumed = []
    monkeypatch.setattr(
        "src.client.ui.layouts.gml_layout.suspend_gml_layout", lambda: "layout-token"
    )
    monkeypatch.setattr(
        "src.client.ui.layouts.gml_layout.resume_gml_layout", resumed.append
    )
    imgui_stub = SimpleNamespace(
        get_window_pos=Mock(return_value=SimpleNamespace(x=0.0, y=0.0)),
        set_cursor_screen_pos=Mock(),
        begin_disabled=Mock(),
        end_disabled=Mock(),
        button=Mock(side_effect=RuntimeError("draw failed")),
        HoveredFlags_=SimpleNamespace(allow_when_disabled=7),
        is_item_hovered=Mock(return_value=False),
        set_tooltip=Mock(),
    )
    monkeypatch.setattr(panel_module, "imgui", imgui_stub)

    with pytest.raises(RuntimeError, match="draw failed"):
        panel._render_apply_button(state_with_modes(), context(), "UKR")

    assert resumed == ["layout-token"]
