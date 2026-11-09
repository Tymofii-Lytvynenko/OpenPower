from contextlib import nullcontext
from types import SimpleNamespace

import pytest

import src.client.ui.layouts.gml_message_geometry as message_geometry
from src.client.ui.layouts.gml_layout import GMLLayoutSession, get_gml_layout
from src.client.ui.layouts.gml_message_geometry import (
    apply_gml_message_geometry,
    geometry_for_gml_message_height,
    measure_gml_message_geometry,
)


def test_short_message_uses_source_auto_height_and_moves_answers_below_text():
    layout = get_gml_layout("Generic_Message_Window")

    geometry = geometry_for_gml_message_height(
        "Generic_Message_Window",
        text_height=28.0,
        viewport_height=720.0,
    )

    assert geometry.message_height == 32.0
    assert geometry.button_y == 54.0
    assert geometry.window_height == 82.0
    assert geometry.window_height < layout.height


def test_message_expansion_keeps_both_question_answers_aligned():
    geometry = geometry_for_gml_message_height(
        "Generic_Question_Window",
        text_height=160.0,
        viewport_height=720.0,
    )

    assert geometry.message_height == 164.0
    assert geometry.button_y == 186.0
    assert geometry.window_height == 214.0
    assert geometry.button_paths == (
        "Generic_Question_Window/btnOk",
        "Generic_Question_Window/btnCancel",
    )


def test_long_message_is_clamped_to_viewport_and_leaves_a_scrollable_body():
    geometry = geometry_for_gml_message_height(
        "Generic_Message_Window",
        text_height=1200.0,
        viewport_height=600.0,
    )

    assert geometry.window_height == 576.0
    assert geometry.message_height == 526.0
    assert geometry.button_y == 548.0


def test_measure_uses_the_message_width_and_converts_text_to_string(monkeypatch):
    layout = get_gml_layout("Generic_Message_Window")
    message_component = layout.component("Generic_Message_Window/lblMessage")
    measured = {}

    monkeypatch.setattr(message_geometry, "gml_style", nullcontext)

    def calc_text_size(value, *, wrap_width):
        measured.update(value=value, wrap_width=wrap_width)
        return SimpleNamespace(y=31.2)

    monkeypatch.setattr(message_geometry, "imgui", SimpleNamespace(calc_text_size=calc_text_size))

    geometry = measure_gml_message_geometry("Generic_Message_Window", 42, 720.0)

    assert measured == {"value": "42", "wrap_width": message_component.rect.width}
    assert geometry.message_height == 36.0


def test_measure_falls_back_to_source_height_when_text_measurement_is_not_finite(monkeypatch):
    layout = get_gml_layout("Generic_Message_Window")
    message_component = layout.component("Generic_Message_Window/lblMessage")
    monkeypatch.setattr(message_geometry, "gml_style", nullcontext)
    monkeypatch.setattr(
        message_geometry,
        "imgui",
        SimpleNamespace(calc_text_size=lambda *_args, **_kwargs: SimpleNamespace(y=float("nan"))),
    )

    geometry = measure_gml_message_geometry("Generic_Message_Window", "message", 720.0)

    assert geometry.message_height == message_component.rect.height
    assert geometry.window_height == layout.height


def test_measure_rejects_layout_without_a_message_control(monkeypatch):
    monkeypatch.setattr(
        message_geometry,
        "get_gml_layout",
        lambda _template: SimpleNamespace(component=lambda _path: None),
    )

    with pytest.raises(KeyError, match="missing its message control"):
        measure_gml_message_geometry("Broken_Window", "message", 720.0)


@pytest.mark.parametrize(
    "components",
    [
        {"Broken_Window/btnOk": SimpleNamespace(path="Broken_Window/btnOk")},
        {
            "Broken_Window/lblMessage": SimpleNamespace(
                rect=SimpleNamespace(y=20.0, height=28.0)
            )
        },
    ],
)
def test_geometry_rejects_missing_message_or_answer_controls(monkeypatch, components):
    layout = SimpleNamespace(
        width=320,
        height=180,
        component=components.get,
    )
    monkeypatch.setattr(message_geometry, "get_gml_layout", lambda _template: layout)

    with pytest.raises(KeyError, match="missing its message or answer controls"):
        geometry_for_gml_message_height("Broken_Window", 40.0, 720.0)


def test_geometry_uses_original_layout_when_text_height_is_not_finite(monkeypatch):
    message = SimpleNamespace(path="Broken_Window/lblMessage", rect=SimpleNamespace(y=20.0, height=28.0))
    answer = SimpleNamespace(path="Broken_Window/btnOk", rect=SimpleNamespace(y=60.0, height=22.0))
    components = {
        "Broken_Window/lblMessage": message,
        "Broken_Window/btnOk": answer,
    }
    layout = SimpleNamespace(width=320, height=180, component=components.get)
    monkeypatch.setattr(message_geometry, "get_gml_layout", lambda _template: layout)

    geometry = geometry_for_gml_message_height("Broken_Window", float("inf"), 720.0)

    assert geometry.message_height == 28.0
    assert geometry.button_y == 60.0
    assert geometry.window_height == 180.0


def test_geometry_keeps_at_least_one_pixel_of_text_with_a_tiny_viewport(monkeypatch):
    message = SimpleNamespace(path="Tiny_Window/lblMessage", rect=SimpleNamespace(y=30.0, height=28.0))
    answer = SimpleNamespace(path="Tiny_Window/btnOk", rect=SimpleNamespace(y=60.0, height=20.0))
    components = {"Tiny_Window/lblMessage": message, "Tiny_Window/btnOk": answer}
    layout = SimpleNamespace(width=320, height=180, component=components.get)
    monkeypatch.setattr(message_geometry, "get_gml_layout", lambda _template: layout)

    geometry = geometry_for_gml_message_height("Tiny_Window", 1000.0, 12.0)

    assert geometry.window_height == 64.0
    assert geometry.message_height == 1.0
    assert geometry.button_y == 43.0


def test_apply_resizes_message_and_aligns_each_answer_button():
    layout = get_gml_layout("Generic_Question_Window")
    session = GMLLayoutSession(layout, (0.0, 0.0), (layout.width, layout.height))
    geometry = geometry_for_gml_message_height("Generic_Question_Window", 160.0, 720.0)

    apply_gml_message_geometry(session, geometry)

    assert session.rect_for(geometry.message_path).height == geometry.message_height
    assert all(session.rect_for(path).y == geometry.button_y for path in geometry.button_paths)


def test_apply_ignores_missing_or_different_layout_sessions():
    geometry = geometry_for_gml_message_height("Generic_Message_Window", 80.0, 720.0)
    other_layout = get_gml_layout("Generic_Question_Window")
    session = GMLLayoutSession(
        other_layout,
        (0.0, 0.0),
        (other_layout.width, other_layout.height),
    )
    original_rects = {
        path: session.rect_for(path)
        for path in (
            geometry.message_path,
            "Generic_Question_Window/btnOk",
            "Generic_Question_Window/btnCancel",
        )
    }

    apply_gml_message_geometry(None, geometry)
    apply_gml_message_geometry(session, geometry)

    assert {
        path: session.rect_for(path)
        for path in original_rects
    } == original_rects
