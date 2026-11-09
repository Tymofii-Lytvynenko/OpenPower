from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, call

import src.client.ui.panels.military.unit_design_editor as editor_module
from src.client.ui.panels.military.unit_design_editor import UnitDesignEditor


def _imgui_mock(monkeypatch):
    imgui = Mock()
    imgui.WindowFlags_.no_move = 1
    imgui.HoveredFlags_.allow_when_disabled = 1
    imgui.get_scroll_x.return_value = 0.0
    imgui.get_scroll_y.return_value = 0.0
    monkeypatch.setattr(editor_module, "imgui", imgui)
    return imgui


def test_open_resets_draft_and_uses_only_known_roles():
    editor = UnitDesignEditor()
    editor._role = "infantry"
    editor._name = "Old"
    editor._cost = 10.0
    editor._maintenance_cost = 2.0
    editor._pending_submission = object()

    editor.open("unknown-role")

    assert editor._role == "infantry"
    assert editor._name == ""
    assert editor._cost == 0.0
    assert editor._maintenance_cost == 0.0
    assert editor._pending_submission is None
    assert editor._capabilities_by_role == {
        "infantry": dict(editor_module.DEFAULT_ROLE_PROFILES["infantry"].capabilities),
    }
    assert editor._is_open is True

    known_role = next(role for role in editor_module.DEFAULT_ROLE_PROFILES if role != "infantry")
    editor.open(known_role)
    assert editor._role == known_role
    assert known_role in editor._capabilities_by_role


def test_render_submits_authoritative_design_and_cancel_closes(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    imgui.combo.return_value = (True, 1)
    imgui.input_text.return_value = (True, "  Heavy Armor  ")
    imgui.input_float.return_value = (True, 125.0)
    roles = list(editor_module.DEFAULT_ROLE_PROFILES)
    options = [SimpleNamespace(role=role, label=role.title()) for role in roles]
    monkeypatch.setattr(editor_module, "unit_type_options_for_roles", Mock(return_value=options))
    monkeypatch.setattr(editor_module, "render_capability_rows", Mock())
    _draw_model = Mock()
    _draw_controls = Mock()
    _draw_maintenance = Mock()
    monkeypatch.setattr(UnitDesignEditor, "_render_model_placeholder", _draw_model)
    monkeypatch.setattr(UnitDesignEditor, "_render_unavailable_model_controls", _draw_controls)
    monkeypatch.setattr(UnitDesignEditor, "_render_maintenance_field", _draw_maintenance)
    ui = Mock()
    ui.toggle.return_value = (False, False)
    ui.path.side_effect = lambda path: path
    ui.button.side_effect = [True, False]
    monkeypatch.setattr(editor_module, "GMLWidgets", Mock(return_value=ui))
    open_state = {"value": True}

    @contextmanager
    def window_context(*_args, **_kwargs):
        yield open_state["value"]

    monkeypatch.setattr(editor_module.WindowManager, "window", window_context)
    client = Mock()
    client.player_id = "player-1"
    context = SimpleNamespace(net_client=client, is_own_country=True, target_tag="ukr")
    state = SimpleNamespace(tables={})
    editor = UnitDesignEditor()
    editor.open("invalid")
    editor._role = "not-in-the-role-catalog"

    editor.render(state, context)

    assert editor._role == roles[1]
    assert editor._name == "  Heavy Armor  "
    assert editor._cost == 125.0
    assert editor._pending_submission.display_name == "Heavy Armor"
    action = client.send_action.call_args.args[0]
    assert action.country_tag == "UKR"
    assert action.class_name == roles[1]
    assert action.display_name == "Heavy Armor"
    assert action.stats["cost"] == 125.0
    assert action.stats["maintenance_cost"] == 0.0
    assert _draw_model.call_args.args == (ui, editor_module.DEFAULT_ROLE_PROFILES[roles[1]].domain)
    _draw_controls.assert_called_once_with(ui)
    _draw_maintenance.assert_called_once_with(ui)
    assert ui.button.call_args_list[0].kwargs["enabled"] is True

    open_state["value"] = False
    editor.render(state, context)
    assert editor._is_open is False


def test_render_skips_closed_editor_and_disables_submission_outside_own_country(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    editor = UnitDesignEditor()
    editor.render(SimpleNamespace(tables={}), SimpleNamespace())
    assert imgui.begin.call_count == 0

    editor.open()
    imgui.combo.return_value = (False, 0)
    imgui.input_text.return_value = (False, "")
    imgui.input_float.return_value = (False, 0.0)
    monkeypatch.setattr(editor_module, "render_capability_rows", Mock())
    monkeypatch.setattr(UnitDesignEditor, "_render_model_placeholder", Mock())
    monkeypatch.setattr(UnitDesignEditor, "_render_unavailable_model_controls", Mock())
    monkeypatch.setattr(UnitDesignEditor, "_render_maintenance_field", Mock())
    ui = Mock()
    ui.toggle.return_value = (False, False)
    ui.path.side_effect = lambda path: path
    ui.button.side_effect = [False, True]
    monkeypatch.setattr(editor_module, "GMLWidgets", Mock(return_value=ui))

    @contextmanager
    def opened_window(*_args, **_kwargs):
        yield True

    monkeypatch.setattr(editor_module.WindowManager, "window", opened_window)
    editor.render(
        SimpleNamespace(tables={}),
        SimpleNamespace(net_client=Mock(), is_own_country=False, target_tag="USA"),
    )

    assert ui.button.call_args_list[0].kwargs["enabled"] is False
    assert ui.button.call_args_list[0].kwargs["tooltip"] == "Enter a name and positive cost in your own country."
    assert editor._is_open is False


def test_render_closes_after_authoritative_design_is_observed(monkeypatch):
    editor = UnitDesignEditor()
    editor.open("infantry")
    editor._pending_submission = editor_module._PendingDesignSubmission(
        "USA", "Recon", frozenset({"old-id"}),
    )
    designs = SimpleNamespace(
        is_empty=Mock(return_value=False),
        to_dicts=Mock(return_value=[{"id": "new-id", "country_id": "USA", "display_name": "Recon"}]),
    )
    window = Mock(side_effect=AssertionError("The acknowledged design should close the editor before rendering."))
    monkeypatch.setattr(editor_module.WindowManager, "window", window)

    editor.render(
        SimpleNamespace(tables={"unit_designs": designs}),
        SimpleNamespace(net_client=None, is_own_country=True, target_tag="USA"),
    )

    assert editor._is_open is False
    window.assert_not_called()


def test_reset_after_create_waits_for_matching_new_snapshot_row():
    editor = UnitDesignEditor()
    editor.open("infantry")
    editor._name = "Recon"
    editor._cost = 100.0
    editor._maintenance_cost = 3.0
    editor._pending_submission = editor_module._PendingDesignSubmission(
        "UKR", "Recon", frozenset({"old-id"}),
    )

    editor._reset_after_authoritative_create(SimpleNamespace(tables={}))
    editor._reset_after_authoritative_create(SimpleNamespace(tables={"unit_designs": SimpleNamespace(
        is_empty=Mock(return_value=True), to_dicts=Mock(return_value=[]),
    )}))
    designs = SimpleNamespace(
        is_empty=Mock(return_value=False),
        to_dicts=Mock(return_value=[
            {"id": "old-id", "country_id": "UKR", "display_name": "Recon"},
            {"id": "new-id", "country_id": "POL", "display_name": "Recon"},
        ]),
    )
    editor._reset_after_authoritative_create(SimpleNamespace(tables={"unit_designs": designs}))

    assert editor._pending_submission is not None
    assert editor._is_open is True
    designs.to_dicts.return_value.append(
        {"id": "new-id-2", "country_id": " ukr ", "display_name": "Recon"},
    )
    editor._reset_after_authoritative_create(SimpleNamespace(tables={"unit_designs": designs}))

    assert editor._pending_submission is None
    assert editor._name == ""
    assert editor._cost == 0.0
    assert editor._maintenance_cost == 0.0
    assert editor._is_open is False


def test_source_frames_and_unavailable_model_controls_render_disabled_state(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    imgui.is_item_hovered.return_value = True
    ui = Mock()
    ui.path.side_effect = lambda path: path

    UnitDesignEditor._draw_source_frames(ui)
    UnitDesignEditor._render_unavailable_model_controls(ui)

    assert ui.frame.call_count == 11
    assert imgui.begin_disabled.call_count == 1
    imgui.end_disabled.assert_called_once_with()
    imgui.set_tooltip.assert_called_once_with("Model part data and assets are unavailable in OpenPower.")
    assert ui.button.call_count == 13
    assert all(call.kwargs["enabled"] is False for call in ui.button.call_args_list)


def test_model_and_maintenance_placeholders_use_layout_and_handle_missing_slots(monkeypatch):
    imgui = _imgui_mock(monkeypatch)
    rect = SimpleNamespace(x=4.0, y=8.0, width=120.0, height=40.0)
    session = SimpleNamespace(window_position=(100.0, 200.0))
    monkeypatch.setattr(editor_module, "active_gml_layout", Mock(side_effect=[None, session, None, session]))
    ui = Mock()
    ui.rect.side_effect = [None, rect, None, rect]
    ui.path.side_effect = lambda path: path

    UnitDesignEditor._render_model_placeholder(ui, "military")
    UnitDesignEditor._render_model_placeholder(ui, "military")
    editor = UnitDesignEditor()
    UnitDesignEditor._render_maintenance_field(editor, ui)
    imgui.input_float.return_value = (True, 7.5)
    editor._render_maintenance_field(ui)

    assert imgui.text_disabled.call_args_list == [
        call("Military role profile"),
        call("3D model assets are unavailable"),
        call("ANNUAL UPKEEP / STRENGTH"),
    ]
    assert editor._maintenance_cost == 7.5
    imgui.set_next_item_width.assert_called_once_with(190.0)
    assert imgui.set_cursor_screen_pos.call_count == 4
