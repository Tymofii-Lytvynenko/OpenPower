from types import SimpleNamespace

import pytest

from src.client.ui.panels.military import battle_position_map


class DrawList:
    def __init__(self):
        self.filled_circles = []
        self.circles = []
        self.texts = []

    def add_circle_filled(self, position, radius, color):
        self.filled_circles.append((position, radius, color))

    def add_circle(self, position, radius, color):
        self.circles.append((position, radius, color))

    def add_text(self, position, color, value):
        self.texts.append((position, color, value))


class FakeImgui:
    def __init__(self, *, clicked=(), hovered=False, size=(200.0, 100.0)):
        self.position = SimpleNamespace(x=100.0, y=50.0)
        self.size = SimpleNamespace(x=size[0], y=size[1])
        self.clicked = set(clicked)
        self.hovered = hovered
        self.draw_list = DrawList()
        self.buttons = []
        self.tooltips = []
        self.positions = []
        self.dummies = []

    def get_cursor_screen_pos(self):
        return self.position

    def get_content_region_avail(self):
        return self.size

    def get_window_draw_list(self):
        return self.draw_list

    def set_cursor_screen_pos(self, position):
        self.positions.append(position)

    def invisible_button(self, label, size, *, test_id):
        self.buttons.append((label, size, test_id))
        return test_id in self.clicked

    def is_item_hovered(self):
        return self.hovered

    def set_tooltip(self, text):
        self.tooltips.append(text)

    @staticmethod
    def get_color_u32(color):
        return color

    def dummy(self, size):
        self.dummies.append(size)


def group(country, side, unit_type, positions):
    return {
        "country_id": country,
        "side": side,
        "unit_type": unit_type,
        "relative_positions": positions,
    }


def install_imgui(monkeypatch, **kwargs):
    fake = FakeImgui(**kwargs)
    monkeypatch.setattr(battle_position_map, "imgui", fake)
    return fake


def test_empty_and_non_finite_positions_show_empty_state(monkeypatch):
    empty_states = []
    monkeypatch.setattr(battle_position_map, "draw_empty_state", empty_states.append)
    install_imgui(monkeypatch)

    battle_position_map.render_battle_positions([])
    battle_position_map.render_battle_positions([
        group("A", "A", "infantry", [(float("nan"), 1), (2, float("inf"))]),
    ])

    assert empty_states == [
        "No observed force coordinates are available.",
        "No observed force coordinates are available.",
    ]


def test_antimeridian_positions_render_markers_select_and_highlight(monkeypatch):
    fake = install_imgui(
        monkeypatch,
        clicked={"battle.inspection.map.A.infantry.1"},
        hovered=True,
    )
    selected = []

    battle_position_map.render_battle_positions(
        [
            group("A", "SIDE_A", "infantry", [(float("nan"), 0), (0, 179)]),
            group("B", "B", "armor", [(10, -179)]),
        ],
        own_side="A",
        selected_force=("A", "infantry"),
        on_select=selected.append,
    )

    assert [button[2] for button in fake.buttons] == [
        "battle.inspection.map.A.infantry.1",
        "battle.inspection.map.B.armor.0",
    ]
    assert selected == [("A", "infantry")]
    assert fake.tooltips == ["A · infantry", "B · armor"]
    assert fake.draw_list.filled_circles == [
        ((112.0, 138.0), 4.0, (0.3, 0.75, 1.0, 1.0)),
        ((288.0, 62.0), 4.0, (1.0, 0.5, 0.3, 1.0)),
    ]
    assert fake.draw_list.circles == [
        ((112.0, 138.0), 7.0, (1.0, 0.95, 0.4, 1.0)),
    ]
    assert [entry[2] for entry in fake.draw_list.texts] == ["A", "B"]
    assert fake.positions[-1] == fake.position
    assert fake.dummies == [(200.0, 100.0)]


def test_single_point_uses_center_and_click_without_callback_is_safe(monkeypatch):
    fake = install_imgui(monkeypatch, clicked={"battle.inspection.map.C.cavalry.0"}, size=(0, -5))

    battle_position_map.render_battle_positions([
        group("C", "SIDE_A", "cavalry", [(5, 5)]),
    ])

    assert fake.draw_list.filled_circles == [
        ((100.5, 50.5), 4.0, (0.3, 0.75, 1.0, 1.0)),
    ]
    assert fake.dummies == [(1.0, 1.0)]


@pytest.mark.parametrize("count", [11, 12])
def test_country_labels_are_omitted_at_twelve_or_more_markers(monkeypatch, count):
    fake = install_imgui(monkeypatch)
    positions = [(index, index) for index in range(count)]

    battle_position_map.render_battle_positions([
        group("A", "A", "infantry", positions),
    ])

    assert len(fake.draw_list.filled_circles) == count
    assert len(fake.draw_list.texts) == (count if count < 12 else 0)
