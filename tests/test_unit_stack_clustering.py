from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from imgui_bundle import imgui

from src.client.renderers.unit_batch_renderer import UnitBatchRenderer
from src.client.renderers.unit_flag_atlas import FlagAtlasEntry
from src.client.renderers.unit_projection import ProjectedUnit, UnitProjectionService
from src.client.renderers.unit_renderer import UnitRenderer


def _unit(unit_id: str, owner: str, strength: int, screen_x: float = 100.0) -> ProjectedUnit:
    return ProjectedUnit(
        unit_id=unit_id,
        owner=owner,
        unit_type="infantry",
        strength=strength,
        current_region_id=1,
        target_region_id=0,
        screen_x=screen_x,
        screen_y=100.0,
        distance_to_camera=0.0,
        width=20.0,
        height=14.0,
        movement_progress=0.0,
        is_moving=False,
    )


def test_projected_unit_stacks_carry_combined_strength_and_distinct_owners() -> None:
    service = UnitProjectionService.__new__(UnitProjectionService)
    first = _unit("u1", "AAA", 120)
    second = _unit("u2", "BBB", 80)
    third = _unit("u3", "AAA", 50)
    separated = _unit("u4", "CCC", 70, screen_x=500.0)

    service._apply_stack_offsets([first, second, third, separated])

    for unit in (first, second, third):
        assert unit.stack_count == 3
        assert unit.stack_strength == 250
    assert separated.stack_count == 1
    assert separated.stack_strength == 70

    entries = {
        "AAA": FlagAtlasEntry(0.1, 0.2, 0.3, 0.4),
        "BBB": FlagAtlasEntry(0.5, 0.6, 0.7, 0.8),
    }
    flags = SimpleNamespace(entry_for=lambda owner: entries[owner])
    vertices = UnitBatchRenderer.__new__(UnitBatchRenderer)._build_vertices([first, second], flags)
    assert tuple(vertices[0, 2:4]) == (0.1, 0.4)
    assert tuple(vertices[6, 2:4]) == (0.5, 0.8)


def test_stack_badge_displays_unit_count_and_combined_strength() -> None:
    renderer = UnitRenderer.__new__(UnitRenderer)
    draw_list = Mock()

    with (
        patch.object(imgui, "calc_text_size", return_value=SimpleNamespace(x=36.0, y=12.0)),
        patch.object(imgui, "get_color_u32", return_value=1),
    ):
        renderer._draw_stack_badge(draw_list, 20.0, 30.0, 3, 1250)

    badge_text = draw_list.add_text.call_args.args[2]
    assert badge_text == "3 · 1,250"
