from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.client.ui.panels.politics import treaty_participant_dialog as dialog_module
from src.client.ui.panels.politics.treaty_participant_dialog import TreatyParticipantDialog


def install_dialog(monkeypatch, *, window_open=True, layout=None):
    imgui = Mock()
    imgui.ChildFlags_.borders = 1
    imgui.get_content_region_avail.return_value = SimpleNamespace(x=140)
    imgui.get_io.return_value.key_ctrl = False
    imgui.get_io.return_value.key_shift = False
    imgui.selectable.return_value = (False, None)
    imgui.begin_child.return_value = True
    imgui.button.return_value = False
    monkeypatch.setattr(dialog_module, "imgui", imgui)
    monkeypatch.setattr(dialog_module, "active_gml_layout", lambda: layout)

    @contextmanager
    def window(*_args, **_kwargs):
        yield window_open

    monkeypatch.setattr(dialog_module.WindowManager, "window", staticmethod(window))
    dialog = TreatyParticipantDialog()
    dialog._flags.draw_flag = Mock()
    return dialog, imgui


def install_country_catalog(monkeypatch):
    names = {"UKR": "Ukraine", "POL": "Poland", "DEU": "Germany"}
    active = ["UKR", "POL", "DEU"]
    active_lookup = Mock(return_value=active)
    name_lookup = Mock(side_effect=lambda _state, tag: names.get(tag, tag))
    monkeypatch.setattr(dialog_module, "active_country_tags", active_lookup)
    monkeypatch.setattr(dialog_module, "resolve_country_name", name_lookup)
    return active_lookup, name_lookup


def test_open_copies_draft_state_and_clears_stale_selections():
    dialog = TreatyParticipantDialog()
    dialog._selected_by_list["a"].add("STALE")
    dialog._selection_anchors["available"] = "STALE"
    side_a = {"UKR"}

    dialog.open(
        side_a=side_a, side_b={"POL"}, two_sided=True,
        protected_a={"UKR"}, protected_b=set(), ineligible_tags=frozenset({"DEU"}),
    )
    side_a.add("POL")

    assert dialog.is_open is True
    assert dialog._side_a == {"UKR"}
    assert dialog._side_b == {"POL"}
    assert dialog._two_sided is True
    assert dialog._protected_a == {"UKR"}
    assert dialog._ineligible_tags == {"DEU"}
    assert dialog._selected_by_list == {"available": set(), "a": set(), "b": set()}
    assert dialog._selection_anchors == {"available": "", "a": "", "b": ""}


def test_result_resolution_keeps_rejected_draft_open_and_closes_applied_draft():
    dialog = TreatyParticipantDialog()
    dialog.open(side_a={"UKR"}, side_b=set(), two_sided=False, protected_a=set(), protected_b=set())
    dialog._waiting_for_result = True

    dialog.resolve_result(applied=False)

    assert dialog.is_open is True
    assert dialog._waiting_for_result is False
    dialog._waiting_for_result = True
    dialog.resolve_result(applied=True)
    assert dialog.is_open is False
    assert dialog._waiting_for_result is False
    dialog.resolve_result(applied=True)


def test_dismiss_and_ineligible_removal_clear_staged_members_and_selection():
    dialog = TreatyParticipantDialog()
    dialog.open(
        side_a={"UKR", "DEU"}, side_b={"POL", "DEU"}, two_sided=True,
        protected_a=set(), protected_b=set(), ineligible_tags={"DEU"},
    )
    dialog._selected_by_list["a"].add("DEU")
    dialog._selected_by_list["b"].add("DEU")
    dialog.mark_ineligible(frozenset({"UKR"}))

    dialog.remove_ineligible()

    assert dialog._side_a == set()
    assert dialog._side_b == {"POL"}
    assert dialog._selected_by_list["a"] == set()
    assert dialog._selected_by_list["b"] == set()
    assert dialog._ineligible_tags == set()
    dialog.dismiss()
    assert dialog.is_open is False


def test_render_closed_dialog_returns_without_opening_a_window(monkeypatch):
    dialog, _imgui = install_dialog(monkeypatch)

    assert dialog.render(SimpleNamespace(tables={})) is None


def test_render_one_sided_dialog_resizes_source_frame_and_marks_unknown_members(monkeypatch):
    layout = Mock()
    layout.rect_for.return_value = SimpleNamespace(height=91)
    dialog, imgui = install_dialog(monkeypatch, layout=layout)
    install_country_catalog(monkeypatch)
    dialog.open(
        side_a={"UKR", "OLD"}, side_b=set(), two_sided=False,
        protected_a={"UKR"}, protected_b=set(),
    )

    result = dialog.render(SimpleNamespace(), ineligible_tags={"POL"})

    assert result is None
    assert dialog._ineligible_tags == {"OLD", "POL"}
    layout.rect_for.assert_called_once_with(f"{dialog._ROOT}/frmUnselected/lstUnselected")
    layout.resize_component.assert_called_once_with(
        f"{dialog._ROOT}/frmSideA/lstSelectedA", height=91,
    )
    list_calls = [call.kwargs["test_id"] for call in imgui.begin_child.call_args_list]
    assert list_calls == [
        "treaty.participants.list.available", "treaty.participants.list.a",
    ]
    labels = [call.args[0] for call in imgui.selectable.call_args_list]
    assert any("POL  Poland  [INELIGIBLE]" in label for label in labels)
    assert not any("Side B" in call.args for call in imgui.text_disabled.call_args_list)
    assert imgui.begin_disabled.call_args_list[0].args == (False,)
    assert imgui.begin_disabled.call_args_list[-1].args == (False,)
    assert imgui.end_disabled.call_count == 6

    dialog._side_a = {"UKR"}
    imgui.begin_disabled.reset_mock()
    dialog.render(SimpleNamespace(), ineligible_tags={"POL"})
    assert imgui.begin_disabled.call_args_list[0].args == (False,)
    assert imgui.begin_disabled.call_args_list[-1].args == (True,)


def test_render_two_sided_dialog_returns_committed_members_and_waits_for_result(monkeypatch):
    dialog, imgui = install_dialog(monkeypatch)
    install_country_catalog(monkeypatch)
    imgui.button.side_effect = lambda _label, **kwargs: kwargs.get("test_id") == "treaty.participants.apply"
    dialog.open(
        side_a={"UKR"}, side_b={"POL"}, two_sided=True,
        protected_a={"UKR"}, protected_b={"POL"},
    )

    result = dialog.render(SimpleNamespace())

    assert result == ({"UKR"}, {"POL"})
    assert dialog._waiting_for_result is True
    list_ids = [call.kwargs["test_id"] for call in imgui.begin_child.call_args_list]
    assert list_ids == [
        "treaty.participants.list.available", "treaty.participants.list.a",
        "treaty.participants.list.b",
    ]
    assert imgui.button.call_args_list[-1].kwargs["test_id"] == "treaty.participants.apply"
    assert imgui.begin_disabled.call_args_list[0].args == (False,)
    assert imgui.begin_disabled.call_args_list[-1].args == (False,)


def test_render_closes_and_clears_wait_state_when_window_is_closed(monkeypatch):
    dialog, _imgui = install_dialog(monkeypatch, window_open=False)
    dialog.open(side_a={"UKR"}, side_b=set(), two_sided=False, protected_a=set(), protected_b=set())
    dialog._waiting_for_result = True

    assert dialog.render(SimpleNamespace(tables={})) is None
    assert dialog.is_open is False
    assert dialog._waiting_for_result is False


@pytest.mark.parametrize("child_open", [False, True])
def test_render_country_list_handles_child_visibility_and_flag_or_row_selection(monkeypatch, child_open):
    dialog, imgui = install_dialog(monkeypatch)
    dialog.open(side_a=set(), side_b=set(), two_sided=False, protected_a=set(), protected_b=set())
    dialog._ineligible_tags.add("POL")
    dialog._flags.draw_flag.reset_mock()
    imgui.begin_child.return_value = child_open
    imgui.is_item_clicked.side_effect = [True, False]
    imgui.selectable.side_effect = [(False, None), (True, None)]

    dialog._render_country_list(
        "Available countries", ["UKR", "POL"], {"UKR": "Ukraine", "POL": "Poland"},
        list_name="available", selected_test_id="selection", frame_path="root/list",
        heading_path="root/heading",
    )

    imgui.text_disabled.assert_called_once_with("AVAILABLE COUNTRIES", gml_id="root/heading")
    assert dialog._flags.draw_flag.call_count == (2 if child_open else 0)
    assert imgui.end_child.call_count == 1
    if child_open:
        assert dialog._selected_by_list["available"] == {"POL"}
        assert dialog._selection_anchors["available"] == "POL"
        assert imgui.selectable.call_args_list[1].kwargs["size"] == (140.0, 16.0)
    else:
        imgui.selectable.assert_not_called()


def test_transfer_buttons_enable_only_available_unprotected_moves(monkeypatch):
    dialog, imgui = install_dialog(monkeypatch)
    dialog._two_sided = True
    dialog._side_a = {"A"}
    dialog._side_b = {"B"}
    dialog._protected_a = {"A"}
    dialog._protected_b = {"B"}
    dialog._selected_by_list = {"available": {"C"}, "a": {"A"}, "b": {"B"}}

    dialog._render_transfer_buttons()

    ids = [call.kwargs["test_id"] for call in imgui.button.call_args_list]
    assert ids == [
        "treaty.participants.add_a", "treaty.participants.remove_a",
        "treaty.participants.add_b", "treaty.participants.remove_b",
        "treaty.participants.move_a_to_b", "treaty.participants.move_b_to_a",
    ]
    assert imgui.begin_disabled.call_args_list == [
        ((False,), {}), ((True,), {}), ((False,), {}), ((True,), {}), ((True,), {}), ((True,), {}),
    ]
    assert imgui.end_disabled.call_count == 6


@pytest.mark.parametrize(
    ("test_id", "expected_a", "expected_b", "expected_available"),
    [
        ("treaty.participants.add_a", {"A", "C"}, {"B"}, set()),
        ("treaty.participants.remove_a", set(), {"B"}, {"C"}),
        ("treaty.participants.add_b", {"A"}, {"B", "C"}, set()),
        ("treaty.participants.remove_b", {"A"}, set(), {"C"}),
        ("treaty.participants.move_a_to_b", set(), {"A", "B"}, {"C"}),
        ("treaty.participants.move_b_to_a", {"A", "B"}, set(), {"C"}),
    ],
)
def test_transfer_button_callbacks_stage_each_participant_move(monkeypatch, test_id, expected_a, expected_b, expected_available):
    dialog, imgui = install_dialog(monkeypatch)
    dialog._two_sided = True
    dialog._side_a = {"A"}
    dialog._side_b = {"B"}
    dialog._selected_by_list = {"available": {"C"}, "a": {"A"}, "b": {"B"}}
    imgui.button.side_effect = lambda _label, **kwargs: kwargs.get("test_id") == test_id

    dialog._render_transfer_buttons()

    assert dialog._side_a == expected_a
    assert dialog._side_b == expected_b
    assert dialog._selected_by_list["available"] == expected_available


def test_move_helpers_preserve_protected_members_and_ignore_disabled_side_b():
    dialog = TreatyParticipantDialog()
    dialog.open(
        side_a={"A", "LOCKED"}, side_b={"B", "LOCKED_B"}, two_sided=True,
        protected_a={"LOCKED"}, protected_b={"LOCKED_B"}, ineligible_tags={"A", "B"},
    )
    dialog._selected_by_list["a"] = {"A", "LOCKED"}
    dialog._selected_by_list["b"] = {"B", "LOCKED_B"}

    dialog._move_to_available("a")
    dialog._move_to_available("b")
    assert dialog._side_a == {"LOCKED"}
    assert dialog._side_b == {"LOCKED_B"}
    assert dialog._ineligible_tags == set()
    assert dialog._selected_by_list["a"] == {"LOCKED"}
    assert dialog._selected_by_list["b"] == {"LOCKED_B"}

    dialog._selected_by_list["available"] = {"A"}
    dialog._move_to_side("a")
    assert dialog._side_a == {"A", "LOCKED"}
    assert dialog._side_b == {"LOCKED_B"}
    assert dialog._selected_by_list["available"] == set()

    dialog._selected_by_list["a"].add("A")
    dialog._selected_by_list["b"].add("B")
    dialog._move_between_sides("a", "b")
    dialog._move_between_sides("b", "a")
    assert dialog._side_a == {"B", "LOCKED"}
    assert dialog._side_b == {"A", "LOCKED_B"}

    dialog._two_sided = False
    before = (set(dialog._side_a), set(dialog._side_b))
    dialog._move_to_side("b")
    dialog._move_to_available("b")
    dialog._move_between_sides("a", "b")
    assert (dialog._side_a, dialog._side_b) == before


def test_selection_supports_plain_control_toggle_and_shift_range(monkeypatch):
    dialog, imgui = install_dialog(monkeypatch)
    tags = ["A", "B", "C", "D"]

    dialog._select_country("available", tags, "B")
    assert dialog._selected_by_list["available"] == {"B"}
    imgui.get_io.return_value.key_ctrl = True
    dialog._select_country("available", tags, "D")
    assert dialog._selected_by_list["available"] == {"B", "D"}
    dialog._select_country("available", tags, "B")
    assert dialog._selected_by_list["available"] == {"D"}
    imgui.get_io.return_value.key_ctrl = False
    imgui.get_io.return_value.key_shift = True
    dialog._selection_anchors["available"] = "D"
    dialog._select_country("available", tags, "B")
    assert dialog._selected_by_list["available"] == {"B", "C", "D"}


def test_country_options_pair_active_tags_with_resolved_names(monkeypatch):
    active_lookup, name_lookup = install_country_catalog(monkeypatch)
    state = object()

    options = TreatyParticipantDialog._country_options(state)

    assert options == [("UKR", "Ukraine"), ("POL", "Poland"), ("DEU", "Germany")]
    active_lookup.assert_called_once_with(state)
    assert name_lookup.call_count == 3
