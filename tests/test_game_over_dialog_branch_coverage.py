from contextlib import contextmanager, nullcontext
from types import SimpleNamespace

import pytest

from src.client.ui.components.shared import game_over_dialog as dialog_module
from src.client.ui.components.shared.game_over_dialog import GameOverDialog


class FakePresenter:
    def __init__(self, campaign=None, objectives=()):
        self.campaign = campaign
        self.objectives = objectives

    def latest_campaign(self, _state, _country_tag):
        return self.campaign

    def build_overview(self, _state, _country_tag):
        return SimpleNamespace(campaign=self.campaign, objectives=self.objectives)


class FakeWidgets:
    def __init__(self, *, button_result=False, calls=None):
        self.button_result = button_result
        self.calls = calls if calls is not None else []

    def frame(self, slot):
        self.calls.append(("frame", slot))

    def text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))

    def button(self, *args, **kwargs):
        self.calls.append(("button", args, kwargs))
        return self.button_result

    def path(self, path):
        return f"Game_Over_Window/{path}"


def native_ui(**overrides):
    methods = {
        "WindowFlags_": SimpleNamespace(no_resize=8),
        "get_main_viewport": lambda: SimpleNamespace(size=SimpleNamespace(x=1280, y=720)),
        "get_style": lambda: SimpleNamespace(font_scale_main=1.0, font_scale_dpi=1.0),
        "set_cursor_pos": lambda *_args: None,
        "get_cursor_pos_x": lambda: 0.0,
        "push_font": lambda *_args: None,
        "pop_font": lambda: None,
        "push_text_wrap_pos": lambda *_args: None,
        "pop_text_wrap_pos": lambda: None,
        "text_wrapped": lambda *_args, **_kwargs: None,
        "text_disabled": lambda *_args, **_kwargs: None,
    }
    methods.update(overrides)
    return SimpleNamespace(**methods)


@pytest.mark.parametrize(
    "campaign, expected",
    [
        (None, False),
        ({"outcome": "ongoing"}, False),
        ({"outcome": "VICTORY"}, True),
        ({"outcome": "defeat", "sandbox_continuation": False}, True),
        ({"outcome": "draw", "sandbox_continuation": True}, False),
        ({"outcome": "unknown"}, False),
    ],
)
def test_game_over_detection_requires_a_terminal_non_sandbox_campaign(campaign, expected):
    dialog = GameOverDialog()
    dialog._presenter = FakePresenter(campaign)

    assert dialog.is_game_over(object(), "AAA") is expected


def test_render_dismisses_nonterminal_results_and_resets_dismissal(monkeypatch):
    dialog = GameOverDialog()
    dialog._presenter = FakePresenter({"id": "campaign", "outcome": "ongoing"})
    dialog._dismissed_result = "previous:victory"

    assert dialog.render(object(), "AAA", on_return_to_menu=lambda: None) is False
    assert dialog._dismissed_result is None


def test_render_skips_a_result_the_user_already_dismissed():
    dialog = GameOverDialog()
    dialog._presenter = FakePresenter({"id": "campaign", "outcome": "VICTORY"})
    dialog._dismissed_result = "campaign:victory"

    assert dialog.render(object(), "AAA", on_return_to_menu=lambda: None) is False


def test_render_finishes_when_window_is_closed_by_its_close_control(monkeypatch):
    calls = []
    dialog = GameOverDialog()
    dialog._presenter = FakePresenter({"id": "c1", "outcome": "defeat"})
    monkeypatch.setattr(dialog_module, "imgui", native_ui())

    @contextmanager
    def closed_window(*args, **kwargs):
        calls.append((args, kwargs))
        yield False

    monkeypatch.setattr(dialog_module.WindowManager, "window", staticmethod(closed_window))

    result = dialog.render(object(), "AAA", on_return_to_menu=lambda: calls.append("menu"))

    assert result is False
    assert dialog._dismissed_result == "c1:defeat"
    assert calls[-1] == "menu"
    assert calls[0][1]["test_id"] == "game_over.dialog"


@pytest.mark.parametrize("button_result", [False, True])
def test_render_draws_outcome_and_finishes_only_when_menu_button_is_clicked(monkeypatch, button_result):
    calls = []
    ui = FakeWidgets(button_result=button_result, calls=calls)
    dialog = GameOverDialog()
    dialog._presenter = FakePresenter(
        {
            "id": "campaign-7",
            "outcome": "victory",
            "outcome_reason": "All objectives complete.",
            "started_at_minute": 100,
        },
        objectives=[{"id": "goal", "status": "completed", "title": "Win"}],
    )
    monkeypatch.setattr(dialog_module, "imgui", native_ui())
    monkeypatch.setattr(dialog_module, "WindowManager", SimpleNamespace(window=lambda *args, **kwargs: nullcontext(True)))
    monkeypatch.setattr(dialog_module, "GMLWidgets", lambda _template: ui)
    monkeypatch.setattr(GameOverDialog, "_render_summary", staticmethod(lambda _ui, summary: calls.append(("summary", summary))))
    monkeypatch.setattr(
        GameOverDialog,
        "_render_objectives",
        staticmethod(lambda _state, _ui, objectives, started_at: calls.append(("objectives", objectives, started_at))),
    )

    result = dialog.render(object(), "AAA", on_return_to_menu=lambda: calls.append("menu"))

    assert result is True
    assert calls[:3] == [
        ("frame", "frmInner"),
        ("frame", "frmInner/frmText"),
        ("frame", "frmInner/frmObjectives"),
    ]
    assert ("summary", "All objectives complete.") in calls
    assert ("objectives", [{"id": "goal", "status": "completed", "title": "Win"}], 100) in calls
    assert ("text", ("frmInner/frmObjectives/lblTitle", "OBJECTIVES"), {}) in calls
    assert ("menu" in calls) is button_result
    assert dialog._dismissed_result == ("campaign-7:victory" if button_result else None)


def test_summary_frame_skips_closed_child_and_restores_font_stacks_on_error(monkeypatch):
    calls = []
    monkeypatch.setattr(dialog_module, "imgui", native_ui(
        set_cursor_pos=lambda value: calls.append(("cursor", value)),
        get_style=lambda: SimpleNamespace(font_scale_main=0.0, font_scale_dpi=0.0),
        push_font=lambda *args: calls.append(("push_font", args)),
        pop_font=lambda: calls.append("pop_font"),
        push_text_wrap_pos=lambda value: calls.append(("push_wrap", value)),
        pop_text_wrap_pos=lambda: calls.append("pop_wrap"),
        text_wrapped=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("text error")),
    ))
    monkeypatch.setattr(dialog_module, "gml_child_frame", lambda *args, **kwargs: nullcontext(False))
    GameOverDialog._render_summary(FakeWidgets(), "Hidden")

    @contextmanager
    def opened_child(*args, **kwargs):
        yield True

    monkeypatch.setattr(dialog_module, "gml_child_frame", opened_child)
    with pytest.raises(RuntimeError, match="text error"):
        GameOverDialog._render_summary(FakeWidgets(), "Visible")

    assert ("push_font", (None, 90.0)) in calls
    assert ("push_wrap", 448.0) in calls
    assert calls[-2:] == ["pop_wrap", "pop_font"]


def test_objective_summary_filters_sorts_and_formats_deadlines(monkeypatch):
    calls = []
    monkeypatch.setattr(dialog_module, "imgui", native_ui(
        set_cursor_pos=lambda value: calls.append(("cursor", value)),
        text_disabled=lambda *args, **kwargs: calls.append(("empty", args, kwargs)),
    ))

    @contextmanager
    def child_frame(*args, **kwargs):
        yield True

    @contextmanager
    def row(*args, **kwargs):
        row_ui = SimpleNamespace(
            text=lambda *values, **options: calls.append(("row_text", values, options))
        )
        yield row_ui

    monkeypatch.setattr(dialog_module, "gml_child_frame", child_frame)
    monkeypatch.setattr(dialog_module, "gml_row", row)
    rows = [
        {"id": "expired", "status": "expired", "title": "Timed out", "deadline_at_minute": 2880},
        {"id": "active", "status": "active", "title": "Hidden"},
        {"id": "done-b", "status": "completed", "title": "Second", "deadline_at_minute": -1},
        {"id": "done-a", "status": "completed", "title": "First", "deadline_at_minute": 100},
        {"id": "failed", "status": "failed", "deadline_at_minute": 900},
    ]

    GameOverDialog._render_objectives(object(), FakeWidgets(), rows, started_at=1440)

    names = [event[1][1] for event in calls if event[0] == "row_text" and event[1][0] == "txtName"]
    times = [event[1][1] for event in calls if event[0] == "row_text" and event[1][0] == "txtTime"]
    assert names == ["First", "Second", "Timed out", "Objective"]
    assert times == ["0 day(s)", "No deadline", "1 day(s)", "0 day(s)"]
    assert all("Hidden" not in event for event in names)


def test_objective_summary_shows_empty_state_and_skips_closed_child(monkeypatch):
    calls = []
    monkeypatch.setattr(dialog_module, "imgui", native_ui(
        set_cursor_pos=lambda value: calls.append(("cursor", value)),
        text_disabled=lambda *args, **kwargs: calls.append(("empty", args, kwargs)),
    ))
    opened = iter([False, True])
    monkeypatch.setattr(dialog_module, "gml_child_frame", lambda *args, **kwargs: nullcontext(next(opened)))

    GameOverDialog._render_objectives(object(), FakeWidgets(), [], started_at=0)
    GameOverDialog._render_objectives(object(), FakeWidgets(), [{"status": "active"}], started_at=0)

    assert ("cursor", (2.0, 2.0)) in calls
    assert any(event[0] == "empty" and event[1][0] == "No completed or timed-out objectives." for event in calls)


def test_finish_marks_the_result_before_returning_to_menu():
    calls = []
    dialog = GameOverDialog()

    dialog._finish("result:victory", lambda: calls.append(dialog._dismissed_result))

    assert dialog._dismissed_result == "result:victory"
    assert calls == ["result:victory"]
