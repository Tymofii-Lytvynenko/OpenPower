from __future__ import annotations

from collections.abc import Iterable, Mapping

from src.client.ui.core.instrumented_imgui import imgui
from src.client.ui.core.primitives import UIPrimitives as Prims
from src.client.ui.core.theme import GAMETHEME


def draw_key_value_rows(rows: Iterable[tuple[str, str]], *, dim_labels: bool = True) -> None:
    for label, value in rows:
        Prims.value_row(label, value, dim_label=dim_labels)


def draw_required_tables(state, required_tables: tuple[str, ...]) -> bool:
    tables = getattr(state, "tables", None)
    missing = tuple(
        name for name in required_tables
        if not isinstance(tables, Mapping) or tables.get(name) is None
    )
    if not missing:
        return True

    draw_empty_state(f"Required game data is unavailable: {', '.join(missing)}.")
    return False


def draw_empty_state(message: str) -> None:
    imgui.push_text_wrap_pos(0.0)
    try:
        imgui.text_colored(GAMETHEME.colors.text_dim, message)
    finally:
        imgui.pop_text_wrap_pos()
