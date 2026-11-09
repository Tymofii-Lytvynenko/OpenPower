from contextlib import contextmanager
from types import SimpleNamespace

from src.client.ui.components.shared import text_notification_dialog as dialog_module
from src.client.ui.components.shared.text_notification_dialog import TextNotificationDialog


def _install_render_surface(monkeypatch, *, opened=True, visible=True, clicked=False):
    events = {"window": [], "child": [], "text": [], "buttons": []}

    @contextmanager
    def popup(*args, **kwargs):
        events["window"].append((args, kwargs))
        yield opened

    @contextmanager
    def child_frame(*args, **kwargs):
        events["child"].append((args, kwargs))
        yield visible

    class Widgets:
        def __init__(self, template):
            events["template"] = template

        def path(self, component_id):
            return f"{events['template']}/{component_id}"

        def button(self, component_id, caption, test_id):
            events["buttons"].append((component_id, caption, test_id))
            return clicked

    imgui = SimpleNamespace(
        WindowFlags_=SimpleNamespace(
            no_title_bar=1,
            no_scrollbar=2,
            no_scroll_with_mouse=4,
        ),
        get_io=lambda: SimpleNamespace(
            display_size=SimpleNamespace(x=1000.0, y=800.0)
        ),
        text_wrapped=lambda *args, **kwargs: events["text"].append((args, kwargs)),
    )
    monkeypatch.setattr(dialog_module, "imgui", imgui)
    monkeypatch.setattr(dialog_module, "center_window", lambda *_args: (321.0, 123.0))
    monkeypatch.setattr(
        dialog_module,
        "WindowManager",
        SimpleNamespace(window=popup),
    )
    monkeypatch.setattr(dialog_module, "GMLWidgets", Widgets)
    monkeypatch.setattr(dialog_module, "gml_child_frame", child_frame)
    return events


def test_enqueue_trims_drops_empty_messages_and_advances_in_order():
    dialog = TextNotificationDialog()

    dialog.show("  First report  ")
    dialog.enqueue("  ")
    dialog.enqueue(None)
    dialog.enqueue("Second report")

    assert dialog._message == "First report"
    assert list(dialog._pending) == ["Second report"]

    dialog._dismiss()
    assert dialog._message == "Second report"
    dialog._dismiss()
    assert dialog._message == ""
    dialog._dismiss()
    assert dialog._message == ""


def test_render_returns_without_opening_a_window_when_queue_is_empty():
    dialog = TextNotificationDialog()

    dialog.render()

    assert dialog._message == ""


def test_render_dismisses_a_closed_popup_and_preserves_the_next_message(monkeypatch):
    events = _install_render_surface(monkeypatch, opened=False)
    dialog = TextNotificationDialog()
    dialog.show("Current")
    dialog.enqueue("Next")

    dialog.render()

    assert dialog._message == "Next"
    assert events["window"][0][0] == ("Dispatch report",)
    assert events["window"][0][1]["x"] == 321.0
    assert events["window"][0][1]["y"] == 123.0
    assert events["window"][0][1]["flags"] == 7
    assert events["child"] == []


def test_render_displays_visible_message_and_waits_for_acknowledgement(monkeypatch):
    events = _install_render_surface(monkeypatch, visible=True, clicked=False)
    dialog = TextNotificationDialog()
    dialog.show("Current report")

    dialog.render()

    assert dialog._message == "Current report"
    assert events["template"] == "Region_Control_Change_Window"
    assert events["child"][0][0] == (
        "Region_Control_Change_Window/frmClip",
    )
    assert events["text"] == [
        (("Current report",), {"test_id": "dispatch.report.content"})
    ]
    assert events["buttons"] == [("btnOk", "OK", "dispatch.report.ok")]


def test_render_hides_clipped_text_and_dismisses_when_acknowledged(monkeypatch):
    events = _install_render_surface(monkeypatch, visible=False, clicked=True)
    dialog = TextNotificationDialog()
    dialog.show("Current report")
    dialog.enqueue("Next report")

    dialog.render()

    assert events["text"] == []
    assert events["buttons"] == [("btnOk", "OK", "dispatch.report.ok")]
    assert dialog._message == "Next report"
