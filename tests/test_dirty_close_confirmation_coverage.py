from contextlib import nullcontext

from src.client.ui.components.shared import dirty_close_confirmation as close_module
from src.client.ui.components.shared.dirty_close_confirmation import (
    CloseDecision,
    DirtyCloseConfirmation,
    SaveConfirmationPreferences,
)


class _ImguiStub:
    def __init__(self, *, remember_choice=False):
        self.remember_choice = remember_choice
        self.calls = []

    def open_popup(self, popup_id):
        self.calls.append(("open_popup", popup_id))

    def checkbox(self, label, value, **kwargs):
        self.calls.append(("checkbox", label, value, kwargs))
        return True, self.remember_choice

    def close_current_popup(self):
        self.calls.append(("close_current_popup",))


class _WidgetsStub:
    def __init__(self, calls, *, apply_clicked=False, discard_clicked=False):
        self.calls = calls
        self.apply_clicked = apply_clicked
        self.discard_clicked = discard_clicked

    def text(self, identifier, value, **kwargs):
        self.calls.append(("text", identifier, value, kwargs))

    def button(self, identifier, label, test_id, *, enabled=True):
        self.calls.append(("button", identifier, label, test_id, enabled))
        clicked = self.apply_clicked if identifier == "btnApply" else self.discard_clicked
        return clicked and enabled


def _install_render_stubs(
    monkeypatch,
    *,
    opened=True,
    remember_choice=False,
    apply_clicked=False,
    discard_clicked=False,
):
    calls = {"modal": [], "widgets": []}
    imgui = _ImguiStub(remember_choice=remember_choice)
    widgets = _WidgetsStub(
        calls["widgets"], apply_clicked=apply_clicked, discard_clicked=discard_clicked
    )

    def popup_modal(*args, **kwargs):
        calls["modal"].append((args, kwargs))
        return nullcontext(opened)

    monkeypatch.setattr(close_module, "imgui", imgui)
    monkeypatch.setattr(close_module, "gml_popup_modal", popup_modal)
    monkeypatch.setattr(close_module, "semantic_region", lambda *_args: nullcontext())
    monkeypatch.setattr(close_module, "GMLWidgets", lambda _root: widgets)
    return calls, imgui


def test_preferences_remember_apply_discard_and_clear_choice():
    preferences = SaveConfirmationPreferences()

    assert preferences.remembered_decision() is None
    preferences.remember_decision(CloseDecision.APPLY, remember=True)
    assert preferences.remembered_decision() is CloseDecision.APPLY
    preferences.remember_decision(CloseDecision.DISCARD, remember=True)
    assert preferences.remembered_decision() is CloseDecision.DISCARD
    preferences.remember_decision(CloseDecision.APPLY, remember=False)
    assert not preferences.do_not_show
    assert preferences.always_apply is False


def test_request_close_honors_pending_and_remembered_preferences():
    preferences = SaveConfirmationPreferences()
    confirmation = DirtyCloseConfirmation("panel.close", "Unsaved changes")

    assert confirmation.request_close(preferences, can_apply=True) is None
    assert confirmation.pending
    assert confirmation.request_close(preferences, can_apply=True) is None

    preferences.remember_decision(CloseDecision.APPLY, remember=True)
    confirmation._pending = False
    assert confirmation.request_close(preferences, can_apply=True) is CloseDecision.APPLY
    assert confirmation.request_close(preferences, can_apply=False) is CloseDecision.DISCARD

    preferences.remember_decision(CloseDecision.DISCARD, remember=True)
    assert confirmation.request_close(preferences, can_apply=True) is CloseDecision.DISCARD


def test_render_without_pending_close_does_not_open_popup(monkeypatch):
    calls, imgui = _install_render_stubs(monkeypatch)
    confirmation = DirtyCloseConfirmation("panel.close", "Unsaved changes")

    assert confirmation.render(SaveConfirmationPreferences(), can_apply=True) is None
    assert calls["modal"] == []
    assert imgui.calls == []


def test_render_waits_for_modal_then_applies_and_resets_state(monkeypatch):
    preferences = SaveConfirmationPreferences()
    confirmation = DirtyCloseConfirmation("panel.close", "Unsaved changes")
    confirmation.request_close(preferences, can_apply=True)
    calls, imgui = _install_render_stubs(monkeypatch, opened=False)

    assert confirmation.render(preferences, can_apply=True) is None
    assert confirmation.pending
    assert confirmation._popup_requested
    assert confirmation.render(preferences, can_apply=True) is None
    assert [call for call in imgui.calls if call[0] == "open_popup"] == [
        ("open_popup", "Save Confirmation##panel.close")
    ]

    _calls, imgui = _install_render_stubs(
        monkeypatch, remember_choice=True, apply_clicked=True
    )
    assert confirmation.render(preferences, can_apply=True) is CloseDecision.APPLY
    assert not confirmation.pending
    assert not confirmation._popup_requested
    assert preferences.remembered_decision() is CloseDecision.APPLY
    assert ("close_current_popup",) in imgui.calls
    assert calls["modal"][0] == (("Save Confirmation##panel.close", "Save_Confirmation_Window"), {"movable": True})


def test_render_disables_apply_but_allows_remembered_discard(monkeypatch):
    preferences = SaveConfirmationPreferences()
    confirmation = DirtyCloseConfirmation("panel.close", "Unsaved changes")
    confirmation.request_close(preferences, can_apply=False)
    calls, imgui = _install_render_stubs(
        monkeypatch,
        remember_choice=True,
        apply_clicked=True,
        discard_clicked=True,
    )

    assert confirmation.render(preferences, can_apply=False) is CloseDecision.DISCARD
    assert not confirmation.pending
    assert preferences.remembered_decision() is CloseDecision.DISCARD
    assert any(call[0] == "button" and call[1] == "btnApply" and not call[-1] for call in calls["widgets"])
    assert any(call[0] == "text" and call[1] == "lblText1" and call[-1]["tooltip"] == confirmation.message for call in calls["widgets"])
    assert ("close_current_popup",) in imgui.calls
