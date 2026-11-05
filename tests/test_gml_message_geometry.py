from src.client.ui.layouts.gml_layout import get_gml_layout
from src.client.ui.layouts.gml_message_geometry import geometry_for_gml_message_height


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
