from contextlib import contextmanager, nullcontext
from types import SimpleNamespace

from src.client.ui.components.shared import generic_question_dialog as question_module
from src.client.ui.components.shared.generic_question_dialog import GenericQuestionDialog


def _install_render_surface(
    monkeypatch,
    *,
    opened=True,
    message_open=True,
    button_results=None,
):
    events = {
        "open_popup": [],
        "measurement": [],
        "modal": [],
        "semantic": [],
        "child": [],
        "text": [],
        "buttons": [],
        "close": [],
    }
    geometry = object()
    button_results = button_results or {}
    imgui = SimpleNamespace(
        open_popup=events["open_popup"].append,
        get_main_viewport=lambda: SimpleNamespace(size=SimpleNamespace(y=640.0)),
        text_wrapped=lambda *args, **kwargs: events["text"].append((args, kwargs)),
        close_current_popup=lambda: events["close"].append(True),
    )

    class Widgets:
        def __init__(self, template):
            self.template = template

        def path(self, component_id):
            return f"{self.template}/{component_id}"

        def button(self, component_id, caption, test_id):
            events["buttons"].append((component_id, caption, test_id))
            return button_results.get(component_id, False)

    @contextmanager
    def popup(popup_id, template, *, message_geometry):
        events["modal"].append((popup_id, template, message_geometry))
        yield opened

    def child_frame(path, *, padding, bordered, test_id):
        events["child"].append((path, padding, bordered, test_id))
        return nullcontext(message_open)

    monkeypatch.setattr(question_module, "imgui", imgui)
    monkeypatch.setattr(
        question_module,
        "measure_gml_message_geometry",
        lambda *args: events["measurement"].append(args) or geometry,
    )
    monkeypatch.setattr(question_module, "gml_popup_modal", popup)
    monkeypatch.setattr(
        question_module,
        "semantic_region",
        lambda *args: events["semantic"].append(args) or nullcontext(),
    )
    monkeypatch.setattr(question_module, "gml_child_frame", child_frame)
    monkeypatch.setattr(question_module, "GMLWidgets", Widgets)
    return events, geometry


def _show_question(dialog, *, accept=None, cancel=None):
    return dialog.show(
        "  Continue with this change?  ",
        accept or (lambda: None),
        cancel or (lambda: None),
        accept_caption="Continue",
        cancel_caption="Go back",
    )


def test_render_waits_for_popup_to_open(monkeypatch):
    events, geometry = _install_render_surface(monkeypatch, opened=False)
    dialog = GenericQuestionDialog("settings.confirm")
    assert _show_question(dialog)

    dialog.render()

    assert events["open_popup"] == ["Question###settings.confirm"]
    assert events["measurement"] == [
        ("Generic_Question_Window", "Continue with this change?", 640.0)
    ]
    assert events["modal"] == [
        ("Question###settings.confirm", "Generic_Question_Window", geometry)
    ]
    assert events["semantic"] == []
    assert events["buttons"] == []
    assert dialog.is_open


def test_render_opens_popup_once_and_skips_unavailable_message_frame(monkeypatch):
    events, _geometry = _install_render_surface(monkeypatch, message_open=False)
    dialog = GenericQuestionDialog("settings.confirm")
    _show_question(dialog)

    dialog.render()
    dialog.render()

    assert events["open_popup"] == ["Question###settings.confirm"]
    assert len(events["modal"]) == 2
    assert events["text"] == []
    assert len(events["buttons"]) == 4
    assert dialog.is_open


def test_render_accepts_and_consumes_the_question_before_callback(monkeypatch):
    events, _geometry = _install_render_surface(
        monkeypatch,
        button_results={"btnOk": True},
    )
    callback_states = []
    dialog = GenericQuestionDialog("settings.confirm")
    _show_question(dialog, accept=lambda: callback_states.append(dialog.is_open))

    dialog.render()

    assert events["text"] == [(("Continue with this change?",), {"test_id": "settings.confirm.message"})]
    assert events["buttons"] == [
        ("btnOk", "Continue", "settings.confirm.yes"),
        ("btnCancel", "Go back", "settings.confirm.no"),
    ]
    assert events["close"] == [True]
    assert callback_states == [False]
    assert not dialog.is_open


def test_render_cancels_when_the_no_button_is_clicked(monkeypatch):
    events, _geometry = _install_render_surface(
        monkeypatch,
        button_results={"btnCancel": True},
    )
    callbacks = []
    dialog = GenericQuestionDialog("settings.confirm")
    _show_question(dialog, cancel=lambda: callbacks.append("cancelled"))

    dialog.render()

    assert events["close"] == [True]
    assert callbacks == ["cancelled"]
    assert not dialog.is_open
