from __future__ import annotations

from collections.abc import Iterable

from imgui_bundle import imgui

from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME


def draw_key_value_rows(rows: Iterable[tuple[str, str]], *, dim_labels: bool = True) -> None:
    for label, value in rows:
        if dim_labels:
            imgui.text_disabled(label)
        else:
            imgui.text(label)
        imgui.same_line()
        Prims.right_align_text(value, GAMETHEME.colors.text_main)


def draw_required_tables(state, required_tables: tuple[str, ...]) -> None:
    pass


def draw_empty_state(message: str) -> None:
    imgui.push_text_wrap_pos(0.0)
    imgui.text_colored(GAMETHEME.colors.text_dim, message)
    imgui.pop_text_wrap_pos()
