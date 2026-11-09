from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl
import pytest

import src.client.renderers.battle_effect_renderer as renderer_module
from src.client.renderers.battle_effect_renderer import BattleEffectRenderer
from src.client.renderers.globe_overlay_projection import ProjectedSurfacePoint
from src.shared.state import GameState
from tests.test_battle_visual_fixtures import (
    build_battle_frame,
    build_camera,
    build_region_frame,
)


def _renderer_and_state(*, battles=None, regions=None):
    state = GameState(tables={
        "battles": build_battle_frame() if battles is None else battles,
        "regions": build_region_frame() if regions is None else regions,
    })
    return BattleEffectRenderer(build_camera(), 2048, 1024, 1.0), state


def _install_imgui(monkeypatch, *, width=800, height=600, opened=True):
    draw_list = Mock()
    flags = SimpleNamespace(
        no_decoration=1,
        no_background=2,
        no_inputs=4,
        no_saved_settings=8,
        no_focus_on_appearing=16,
        no_nav=32,
    )
    imgui = SimpleNamespace(
        WindowFlags_=flags,
        get_io=lambda: SimpleNamespace(display_size=SimpleNamespace(x=width, y=height)),
        begin=Mock(return_value=(opened, None)),
        end=Mock(),
        set_next_window_pos=Mock(),
        set_next_window_size=Mock(),
        get_window_draw_list=Mock(return_value=draw_list),
        get_color_u32=lambda color: color,
    )
    monkeypatch.setattr(renderer_module, "imgui", imgui)
    return imgui, draw_list


def _point(*, clearance=100.0):
    return ProjectedSurfacePoint(
        latitude=0.0,
        longitude=0.0,
        screen_x=400.0,
        screen_y=300.0,
        depth=1.0,
        marker_radius=8.0,
        silhouette_clearance=clearance,
    )


def _stub_projection(renderer, point):
    renderer._projection.prepare = Mock(return_value=True)
    renderer._projection.project_anchors = Mock(
        side_effect=lambda anchors, *_args, **_kwargs: [point for _ in anchors],
    )


def test_render_clears_layout_for_missing_state_and_invalid_viewport(monkeypatch):
    renderer, state = _renderer_and_state()
    renderer._last_layout = (Mock(),)
    imgui, _draw_list = _install_imgui(monkeypatch, width=0, height=600)
    renderer._projection.prepare = Mock(return_value=True)

    renderer.render(None)
    assert renderer.last_layout == ()

    renderer.render(state)

    assert renderer.last_layout == ()
    renderer._projection.prepare.assert_not_called()
    imgui.begin.assert_not_called()


def test_render_skips_anchors_when_camera_projection_is_unavailable(monkeypatch):
    renderer, state = _renderer_and_state()
    imgui, _draw_list = _install_imgui(monkeypatch)
    renderer._projection.prepare = Mock(return_value=False)
    renderer._projection.project_anchors = Mock()

    renderer.render(state)

    assert renderer.last_layout == ()
    renderer._projection.prepare.assert_called_once_with(800, 600)
    renderer._projection.project_anchors.assert_not_called()
    imgui.begin.assert_not_called()


def test_render_projects_and_draws_assault_effects(monkeypatch):
    renderer, state = _renderer_and_state(
        battles=build_battle_frame(mode="assault", status="active"),
    )
    imgui, draw_list = _install_imgui(monkeypatch)
    _stub_projection(renderer, _point())

    renderer.render(state, presentation_total_minutes=12.0)

    assert [placement.battle_id for placement in renderer.last_layout] == ["battle-001"]
    imgui.set_next_window_pos.assert_called_once_with((0, 0))
    imgui.set_next_window_size.assert_called_once_with((800.0, 600.0))
    imgui.begin.assert_called_once()
    imgui.end.assert_called_once_with()
    draw_list.add_circle_filled.assert_called_once()
    assert draw_list.add_circle.call_count == 3
    assert draw_list.add_line.call_count == 2
    draw_list.add_rect_filled.assert_called_once()


def test_render_keeps_a_recent_conclusion_then_expires_it(monkeypatch):
    renderer, state = _renderer_and_state(
        battles=build_battle_frame(status="concluded"),
    )
    _install_imgui(monkeypatch)
    point = _point()
    _stub_projection(renderer, point)
    layout = Mock(return_value=[])
    renderer._layout = layout
    clock = Mock(side_effect=[10.0, 10.5, 12.0])
    monkeypatch.setattr(renderer_module, "time", SimpleNamespace(monotonic=clock))

    renderer.render(state)
    assert renderer.conclusion_cache_size == 1

    state.update_table("battles", state.tables["battles"].head(0))
    renderer.render(state)
    assert [row["id"] for row, _point in layout.call_args_list[1].args[0]] == ["battle-001"]
    assert renderer.conclusion_cache_size == 1

    renderer.render(state)
    assert layout.call_args_list[2].args[0] == []
    assert renderer.conclusion_cache_size == 0


def test_render_evicts_the_oldest_conclusion_when_cache_is_full(monkeypatch):
    renderer, state = _renderer_and_state(
        battles=build_battle_frame(status="concluded"),
    )
    _install_imgui(monkeypatch)
    _stub_projection(renderer, _point())
    renderer._layout = Mock(return_value=[])
    monkeypatch.setattr(renderer_module, "time", SimpleNamespace(monotonic=lambda: 100.0))
    cached_row = {
        "region_id": 1,
        "anchor_latitude": 0.0,
        "anchor_longitude": 0.0,
        "anchor_source": "contact",
        "attacker_side": "USA",
        "defender_side": "CAN",
        "mode": "positional",
        "status": "concluded",
    }
    renderer._conclusion_cache = {
        f"old-{index:03d}": ({**cached_row, "id": f"old-{index:03d}"}, 99.5)
        for index in range(renderer.MAX_CONCLUSION_CACHE)
    }

    renderer.render(state)

    assert renderer.conclusion_cache_size == renderer.MAX_CONCLUSION_CACHE
    assert "old-000" not in renderer._conclusion_cache
    assert "battle-001" in renderer._conclusion_cache


def test_normalization_uses_pixel_region_centers_and_revision_cache():
    battles = build_battle_frame(
        anchor_latitude=None,
        anchor_longitude=None,
        anchor_source="",
    )
    regions = pl.DataFrame([{"id": 1, "center_x": 512.0, "center_y": 256.0}])
    renderer, state = _renderer_and_state(battles=battles, regions=regions)

    rows = renderer._normalize_state(state)

    assert renderer._normalize_state(state) is rows
    assert renderer.normalized_rows is rows
    assert renderer.normalized_cache_key is not None
    assert renderer._anchor_for_row(rows[0]) is not None


def test_render_diagnoses_rows_without_id_or_resolvable_anchor(monkeypatch, caplog):
    battles = pl.DataFrame([
        {
            **build_battle_frame().row(0, named=True),
            "id": "",
            "anchor_latitude": None,
            "anchor_longitude": None,
            "anchor_source": "unknown",
        },
        {
            **build_battle_frame().row(0, named=True),
            "id": "battle-without-anchor",
            "region_id": 99,
            "anchor_latitude": None,
            "anchor_longitude": None,
            "anchor_source": "unknown",
        },
    ])
    regions = pl.DataFrame(schema={"id": pl.Int64})
    renderer, state = _renderer_and_state(battles=battles, regions=regions)
    _install_imgui(monkeypatch)
    _stub_projection(renderer, _point())
    renderer._layout = Mock(return_value=[])

    renderer.render(state)

    assert any("missing_id" in record.message for record in caplog.records)
    assert any("missing_anchor" in record.message for record in caplog.records)
    assert renderer._layout.call_args.args[0] == []


def test_invalid_pixel_region_coordinates_are_isolated(caplog):
    battles = build_battle_frame(anchor_latitude=None, anchor_longitude=None)
    regions = pl.DataFrame([{"id": 1, "center_x": "invalid", "center_y": 10.0}])
    renderer, state = _renderer_and_state(battles=battles, regions=regions)

    renderer._normalize_state(state)

    assert any("invalid_region" in record.message for record in caplog.records)


def test_invalid_anchor_region_id_is_ignored():
    renderer, _state = _renderer_and_state()

    assert renderer._anchor_for_row({
        "anchor_latitude": None,
        "anchor_longitude": None,
        "anchor_source": "unknown",
        "region_id": "invalid",
    }) is None


def test_custom_side_color_resolver_normalizes_and_recovers_from_bad_values(caplog):
    renderer = BattleEffectRenderer(
        build_camera(), 2048, 1024, 1.0,
        color_resolver=lambda _side: (255, 128, 0),
    )
    assert renderer._resolve_side_color("USA") == (1.0, 128 / 255, 0.0, 1.0)

    invalid = BattleEffectRenderer(
        build_camera(), 2048, 1024, 1.0,
        color_resolver=lambda _side: ("red", 0, 0),
    )
    fallback = invalid._resolve_side_color("USA")

    assert len(fallback) == 4
    assert caplog.records[-1].message.startswith("Battle overlay isolated invalid_side_color")


def test_same_side_pair_gets_a_distinct_defender_color():
    resolved = []
    renderer = BattleEffectRenderer(
        build_camera(), 2048, 1024, 1.0,
        color_resolver=lambda side: resolved.append(side) or (20, 40, 60),
    )

    attacker, defender = renderer.side_colors({
        "attacker_side": "USA",
        "defender_side": "USA",
    })

    assert attacker == (20 / 255, 40 / 255, 60 / 255, 1.0)
    assert defender == attacker
    assert resolved == ["USA", "USA", "USA:defender"]


@pytest.mark.parametrize(
    ("mode", "status", "expected"),
    [
        ("invalid", "invalid", "Battle"),
        ("positional", "stalemate", "Stalemate"),
        ("positional", "concluded", "Concluded"),
        ("invalid", "active", "Battle"),
    ],
)
def test_label_for_all_status_and_mode_fallbacks(mode, status, expected):
    assert BattleEffectRenderer._label(mode, status) == expected


def test_side_key_accepts_sequences_and_removes_blank_values():
    assert BattleEffectRenderer._side_key(["can", "", "usa"]) == "CAN,USA"


@pytest.mark.parametrize("status", ["stalemate", "concluded"])
def test_render_uses_distinct_markers_for_stalemate_and_conclusion(monkeypatch, status):
    renderer, state = _renderer_and_state(battles=build_battle_frame(status=status))
    imgui, draw_list = _install_imgui(monkeypatch)
    _stub_projection(renderer, _point())

    renderer.render(state, reduce_motion=True)

    marker_text = draw_list.add_text.call_args_list[0].args[2]
    assert marker_text == ("!" if status == "stalemate" else "×")
    if status == "concluded":
        assert draw_list.add_line.call_count == 2
    imgui.end.assert_called_once_with()


def test_fallback_slot_search_skips_out_of_range_rows_and_handles_full_grid():
    renderer, _state = _renderer_and_state()
    grid = renderer._build_fallback_grid(256, 64, 80.0, 20.0)
    grid.occupied_rows[0] = (1 << grid.columns) - 1

    assert renderer._nearest_fallback_slot(40.0, 10.0, grid) is not None

    grid.occupied_rows[:] = [(1 << grid.columns) - 1] * grid.rows
    assert renderer._nearest_fallback_slot(40.0, 10.0, grid) is None


def test_crowded_layout_evicts_the_oldest_cached_fallback_grid():
    renderer, _state = _renderer_and_state()
    renderer._fallback_slot_layouts = {
        ("seed", index): (1, 1, []) for index in range(8)
    }
    point = _point()
    rows = build_battle_frame(24).to_dicts()
    for row in rows:
        row["anchor_latitude"] = 0.0
        row["anchor_longitude"] = 0.0

    placements = renderer._layout(
        [(row, point) for row in rows], 1280, 720, 0.0, False,
    )

    assert len(placements) == len(rows)
    assert len(renderer._fallback_slot_layouts) == 8
    assert ("seed", 0) not in renderer._fallback_slot_layouts


def test_fallback_slot_collision_retries_after_rejecting_a_candidate():
    renderer, _state = _renderer_and_state()
    renderer._fallback_slot_layouts = {
        ("seed", index): (1, 1, []) for index in range(8)
    }
    point = _point()
    rows = build_battle_frame(9).to_dicts()
    for row in rows:
        row["anchor_latitude"] = 0.0
        row["anchor_longitude"] = 0.0
    collision_checks = 0

    def collide_first_slot(coverage, occupied):
        nonlocal collision_checks
        collision_checks += 1
        if collision_checks == 1:
            return True
        return BattleEffectRenderer._coverage_collides(coverage, occupied)

    renderer._coverage_collides = collide_first_slot

    placements = renderer._layout(
        [(row, point) for row in rows], 1280, 720, 0.0, False,
    )

    assert len(placements) == 9
    assert collision_checks >= 2


def test_longitudes_normalize_across_multiple_world_wraps():
    assert BattleEffectRenderer._normalize_longitude(900.0) == -180.0
    assert BattleEffectRenderer._normalize_longitude(-900.0) == -180.0


def test_diagnostics_log_only_the_first_occurrence(caplog):
    renderer, _state = _renderer_and_state()

    renderer._diagnose("missing_anchor", "battle-1", 7)
    renderer._diagnose("missing_anchor", "battle-1", 7)

    assert len(caplog.records) == 1
