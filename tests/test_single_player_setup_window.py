from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.client.ui.components.shared import (
    single_player_setup_window as single_player_setup_module,
)


class _Widgets:
    def __init__(self, *, combo_result=(False, 0), clicked_slots=()):
        self.combo_result = combo_result
        self.clicked_slots = set(clicked_slots)
        self.frames = []
        self.text = []
        self.combos = []
        self.buttons = []

    def frame(self, slot):
        self.frames.append(slot)

    def text_at(self, slot, value, **kwargs):
        self.text.append((slot, value, kwargs))

    def combo_at(self, *args, **kwargs):
        self.combos.append((args, kwargs))
        return self.combo_result

    def button(self, slot, label, test_id, **kwargs):
        self.buttons.append((slot, label, test_id, kwargs))
        return slot in self.clicked_slots


def _preview(*, duration=60, objectives=None):
    return SimpleNamespace(
        scope="national",
        max_duration_minutes=duration,
        objectives=objectives or (),
    )


def test_render_centers_window_and_dispatches_country_party_profile_and_start(monkeypatch):
    widgets = _Widgets(
        combo_result=(True, 1),
        clicked_slots={
            "frmInner/frmCountrySelection/btnProfile",
            "frmInner/frmSphereControl/btnParty",
            "frmInner/btnStart",
        },
    )
    monkeypatch.setattr(single_player_setup_module, "GMLWidgets", lambda _root: widgets)
    window = single_player_setup_module.SinglePlayerSetupWindow()
    callbacks = [Mock() for _ in range(5)]
    preview = _preview(
        objectives=[SimpleNamespace(title="Secure the capital", deadline="within 30 minute(s)")]
    )

    with patch.object(
        single_player_setup_module.WindowManager,
        "window",
        return_value=nullcontext(True),
    ) as begin:
        window.render(
            1280,
            720,
            [("UKR", "Ukraine")],
            "UKR",
            "Civic Party",
            True,
            preview,
            *callbacks,
        )

    begin.assert_called_once_with(
        "START SINGLE PLAYER",
        x=467.0,
        y=189.5,
        w=346,
        h=341,
        test_id="new_game.panel",
        gml_template="Start_Single_Player",
        follow_position=True,
    )
    callbacks[0].assert_called_once_with("UKR")
    for callback in callbacks[1:4]:
        callback.assert_called_once_with()
    callbacks[4].assert_not_called()
    assert len(widgets.frames) == 12
    assert widgets.combos[0][0][2] == 1
    assert widgets.combos[0][1]["enabled"] is True
    assert any(
        slot == "frmInner/frmCountrySelection/lblTitle" and value == "COUNTRY: UKR"
        for slot, value, _ in widgets.text
    )
    assert any(slot == "frmInner/frmGoals/txtGoal1" and value == "Secure the capital" for slot, value, _ in widgets.text)
    assert any(slot == "frmInner/frmGoals/cboGoal1" and value == "30 min" for slot, value, _ in widgets.text)


def test_render_without_country_keeps_actions_disabled_and_shows_empty_objectives(monkeypatch):
    widgets = _Widgets(combo_result=(True, 0))
    monkeypatch.setattr(single_player_setup_module, "GMLWidgets", lambda _root: widgets)
    window = single_player_setup_module.SinglePlayerSetupWindow()
    on_select_country = Mock()
    callbacks = [Mock() for _ in range(4)]

    with patch.object(
        single_player_setup_module.WindowManager,
        "window",
        return_value=nullcontext(True),
    ):
        window.render(
            800,
            600,
            [],
            None,
            "",
            False,
            _preview(duration=0),
            on_select_country,
            *callbacks,
        )

    on_select_country.assert_called_once_with("")
    for callback in callbacks:
        callback.assert_not_called()
    assert all(not button[3]["enabled"] for button in widgets.buttons)
    assert any(value == "COUNTRY: CHOOSE" for _, value, _ in widgets.text)
    assert any(value == "No limit" for _, value, _ in widgets.text)
    assert any(value == "No configured objectives" for _, value, _ in widgets.text)
    assert any(value == "—" for _, value, _ in widgets.text)


def test_closed_setup_window_runs_back_callback_without_rendering(monkeypatch):
    widgets_factory = Mock()
    monkeypatch.setattr(single_player_setup_module, "GMLWidgets", widgets_factory)
    on_back = Mock()

    with patch.object(
        single_player_setup_module.WindowManager,
        "window",
        return_value=nullcontext(False),
    ):
        single_player_setup_module.SinglePlayerSetupWindow().render(
            1280,
            720,
            [],
            None,
            "",
            False,
            _preview(),
            Mock(),
            Mock(),
            Mock(),
            Mock(),
            on_back,
        )

    on_back.assert_called_once_with()
    widgets_factory.assert_not_called()


def test_compact_deadline_normalizes_supported_formats_and_preserves_other_text():
    assert single_player_setup_module._compact_deadline("within 45 minute(s)") == "45 min"
    assert single_player_setup_module._compact_deadline("game minute 120") == "120 min"
    assert single_player_setup_module._compact_deadline("no deadline") == "—"
    assert single_player_setup_module._compact_deadline("by next election") == "by next election"
