"""Reusable one-shot question with the source Generic_Question_Window canvas."""
from dataclasses import dataclass
from collections.abc import Callable
from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.gml_widgets import GMLWidgets
from src.client.ui.core.testability import semantic_region
from src.client.ui.layouts.gml_layout import gml_child_frame
from src.client.ui.layouts.gml_message_geometry import measure_gml_message_geometry
from src.client.ui.layouts.gml_popup import gml_popup_modal


@dataclass(frozen=True)
class Question:
    message: str
    accept: Callable[[], None]
    cancel: Callable[[], None]
    accept_caption: str
    cancel_caption: str


class GenericQuestionDialog:
    def __init__(self, test_id):
        self.test_id = test_id
        self._question = None
        self._popup_requested = False

    @property
    def is_open(self):
        return self._question is not None

    def show(self, message, on_accept, on_cancel, *, accept_caption="Yes", cancel_caption="No"):
        message = str(message or "").strip()
        if self.is_open or not message:
            return False
        self._question = Question(message, on_accept, on_cancel, str(accept_caption or "Yes"), str(cancel_caption or "No"))
        return True

    def answer(self, accept):
        question = self._question
        self._question = None
        self._popup_requested = False
        # Consume the observer before invocation, including reentrant callbacks.
        if question is not None:
            (question.accept if accept else question.cancel)()

    def render(self):
        if not self.is_open:
            return
        popup_id = "Question###" + self.test_id
        if not self._popup_requested:
            imgui.open_popup(popup_id)
            self._popup_requested = True
        geometry = measure_gml_message_geometry(
            "Generic_Question_Window",
            self._question.message,
            float(imgui.get_main_viewport().size.y),
        )
        decision = None
        with gml_popup_modal(
            popup_id,
            "Generic_Question_Window",
            message_geometry=geometry,
        ) as opened:
            if opened:
                with semantic_region(self.test_id, "Question"):
                    ui = GMLWidgets("Generic_Question_Window")
                    with gml_child_frame(
                        ui.path("lblMessage"),
                        padding=(0.0, 0.0),
                        bordered=False,
                        test_id=self.test_id + ".message.region",
                    ) as message_open:
                        if message_open:
                            imgui.text_wrapped(
                                self._question.message,
                                test_id=self.test_id + ".message",
                            )
                    if ui.button("btnOk", self._question.accept_caption, self.test_id + ".yes"):
                        decision = True
                    if ui.button("btnCancel", self._question.cancel_caption, self.test_id + ".no"):
                        decision = False
                    if decision is not None:
                        imgui.close_current_popup()
        if decision is not None:
            self.answer(decision)
