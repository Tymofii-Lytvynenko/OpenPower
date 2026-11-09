from contextlib import contextmanager
from types import SimpleNamespace

from src.client.ui.panels.military import strategic_planner
from src.client.ui.panels.military.strategic_plan import StrategicPlan
from src.client.ui.panels.military.strategic_planner import StrategicPlanner


class Table:
    def __init__(self, rows):
        self.rows = rows

    def to_dicts(self):
        return self.rows


class Imgui:
    def __init__(self, *, combo_result=(False, 0), checkbox_result=(False, False)):
        self.combo_result = combo_result
        self.checkbox_result = checkbox_result
        self.combos = []
        self.checkboxes = []
        self.texts = []
        self.same_lines = []
        self.item_widths = []

    def combo(self, *args, **kwargs):
        self.combos.append((args, kwargs))
        return self.combo_result

    def checkbox(self, *args, **kwargs):
        self.checkboxes.append((args, kwargs))
        return self.checkbox_result

    def same_line(self, position):
        self.same_lines.append(position)

    def set_next_item_width(self, width):
        self.item_widths.append(width)

    def text(self, value):
        self.texts.append(value)


class Ui:
    def __init__(self, *, combo_at_result=(False, 0), clicked=()):
        self.combo_at_result = combo_at_result
        self.clicked = set(clicked)
        self.texts = []
        self.buttons = []

    def text(self, *args, **kwargs):
        self.texts.append((args, kwargs))

    @staticmethod
    def path(slot):
        return f"gml/{slot}"

    def combo_at(self, *args):
        return self.combo_at_result

    def button(self, slot, label, test_id, **kwargs):
        self.buttons.append((slot, label, test_id, kwargs))
        return test_id in self.clicked


def _open_window(opened=True):
    @contextmanager
    def window(*_args, **_kwargs):
        yield opened

    return window


def state_with_regions(rows):
    return SimpleNamespace(tables={"regions": Table(rows)})


def test_rows_targets_and_open_keep_foreign_target_filter_and_payload_copy():
    planner = StrategicPlanner(object())
    planner.plan = StrategicPlan(country="USA")
    state = state_with_regions([
        {"id": 1, "owner": "USA"},
        {"id": 2, "owner": "CAN"},
        {"id": 3, "owner": ""},
        {"id": 4, "owner": "None"},
    ])
    assert planner._rows(SimpleNamespace(tables={}), "regions") == []
    assert planner._targets(state) == [{"id": 2, "owner": "CAN"}]

    payloads = {"W1": 2}
    planner.open("USA", 2, payload_levels=payloads)
    payloads["W1"] = 1
    assert planner.plan.country == "USA"
    assert planner.plan.target_region == 2
    assert planner.plan.payload_levels == {"W1": 2}
    assert planner.phase == "country"
    assert planner.multiple is False
    assert planner._feedback == ""


def test_plan_skips_unassigned_multiple_targets_and_rejects_stale_payloads():
    weapon = {
        "id": "W1",
        "payload_level": 1,
        "payload_cap": 2,
        "launch_cost": 5.0,
        "weapon_type": "icbm",
    }
    presenter = SimpleNamespace(
        strategic_inventory_for_country=lambda *_: [weapon],
        strategic_launch_preview=lambda *_: {"reasons": [], "target_country_id": "CAN"},
    )
    state = SimpleNamespace(tables={})
    missing_target = StrategicPlan(country="USA", selected_weapons={"W1"})

    actions, reasons = missing_target.actions(state, presenter, "player", multiple=True)

    assert actions == []
    assert reasons == []

    stale_payload = StrategicPlan(
        country="USA",
        target_region=7,
        selected_weapons={"W1"},
        payload_levels={"W1": 3},
    )
    stale_state = SimpleNamespace(
        tables={"countries": Table([{"id": "USA", "money_reserves": 100.0}])}
    )

    actions, reasons = stale_payload.actions(stale_state, presenter, "player")

    assert actions == []
    assert reasons == ["W1: selected payload is no longer available."]


def test_render_dispatches_active_phase_and_ignores_empty_phase():
    planner = StrategicPlanner(object())
    calls = []
    planner._country = lambda state, context: calls.append((state, context))
    planner.render("state", "context")
    assert calls == []

    planner.phase = "country"
    planner.render("state", "context")
    assert calls == [("state", "context")]


def test_country_selection_changes_target_and_enters_specific_or_multiple_modes(monkeypatch):
    fake = Imgui(combo_result=(True, 1))
    monkeypatch.setattr(strategic_planner, "imgui", fake)
    planner = StrategicPlanner(object())
    planner.plan = StrategicPlan(country="USA", target_region=2)
    state = state_with_regions([
        {"id": 1, "owner": "USA"},
        {"id": 2, "owner": "CAN"},
        {"id": 3, "owner": "MEX"},
    ])
    ui = Ui()

    targets, regions = planner._render_country_selection(
        state,
        SimpleNamespace(selected_region_id=77),
        ui,
    )

    assert [row["id"] for row in targets] == [2, 3]
    assert [row["id"] for row in regions] == [3]
    assert planner.plan.target_country == "MEX"
    assert planner.plan.target_region == 3
    assert fake.combos[0][0][2] == ["CAN", "MEX", "Specific location", "Multiple countries"]

    for choice, expected_phase, expected_multiple in (
        (2, "select", False),
        (3, "multiple", True),
    ):
        fake.combo_result = (True, choice)
        planner.phase = "country"
        planner.multiple = False
        planner._render_country_selection(state, SimpleNamespace(selected_region_id=77), Ui())
        assert planner.phase == expected_phase
        assert planner.multiple is expected_multiple
        if expected_phase == "select":
            assert planner._selection_origin == 77


def test_missile_row_labels_use_selected_payload_and_resolve_locations(monkeypatch):
    monkeypatch.setattr(
        strategic_planner,
        "resolve_region_name",
        lambda state, region_id: {4: "Silo", 9: "Target City"}.get(region_id, "Unknown"),
    )
    planner = StrategicPlanner(object())
    planner.plan = StrategicPlan(
        country="USA",
        assignments={"W1": 9},
        payload_levels={"W1": 2},
    )

    assert planner._missile_row_labels(
        object(),
        {"id": "W1", "ready": 3, "quantity": 5, "payload_level": 1, "origin_region_id": 4},
        {1: (100.0, 4.0), 2: (250.0, 5.0)},
    ) == ("W1", "W1 (3/5)", "250 kt", "Silo", "Target City")

    planner.plan.payload_levels.clear()
    assert planner._missile_row_labels(
        object(),
        {"id": "W2", "ready": None, "quantity": 2, "payload_level": 8, "origin_region_id": 0},
        {},
    ) == ("W2", "W2", "—", "—", "—")


def test_assignment_row_toggles_weapon_and_stores_target_assignment(monkeypatch):
    fake = Imgui(combo_result=(False, 1), checkbox_result=(True, True))
    monkeypatch.setattr(strategic_planner, "imgui", fake)
    monkeypatch.setattr(
        strategic_planner.UIPrimitives,
        "fit_text",
        staticmethod(lambda value, width: value),
    )
    planner = StrategicPlanner(object())
    planner.plan = StrategicPlan(country="USA", target_region=2)
    targets = [
        {"id": 2, "owner": "CAN", "name": "North"},
        {"id": 3, "owner": "MEX", "name": "South"},
    ]

    planner._render_assignment_row({"id": "W1", "ready": 4}, targets)

    assert planner.plan.selected_weapons == {"W1"}
    assert planner.plan.assignments == {"W1": 3}
    assert fake.checkboxes[0][0][0] == "W1##W1"
    assert fake.combos[0][0][2] == ["CAN: North", "MEX: South"]
    assert fake.texts == ["Military", "4", "1", "1"]
    assert fake.same_lines == [204, 322, 466, 549, 633]
    assert fake.item_widths == [135]


def test_select_phase_cancels_or_updates_plan_from_foreign_map_selection(monkeypatch):
    @contextmanager
    def opened_window(*args, **kwargs):
        yield True

    monkeypatch.setattr(strategic_planner, "GMLWidgets", lambda root: Ui())
    planner = StrategicPlanner(object())
    planner.plan = StrategicPlan(country="USA", target_region=2)
    planner.phase = "select"
    planner._selection_origin = 10
    planner._window = lambda *args, **kwargs: opened_window()
    state = state_with_regions([
        {"id": 2, "owner": "CAN"},
        {"id": 4, "owner": "MEX"},
    ])

    planner._select(state, SimpleNamespace(selected_region_id=4))
    assert planner.plan.target_region == 4
    assert planner.plan.target_country == "MEX"
    assert planner.phase == "country"

    planner.phase = "select"
    planner._window = lambda *args, **kwargs: opened_window()
    cancel_ui = Ui(clicked={"strategic.target.cancel"})
    monkeypatch.setattr(strategic_planner, "GMLWidgets", lambda root: cancel_ui)
    planner._select(state, SimpleNamespace(selected_region_id=4))
    assert planner.phase == "country"

    planner.phase = "select"
    planner._window = lambda *args, **kwargs: opened_window()
    monkeypatch.setattr(strategic_planner, "GMLWidgets", lambda root: Ui())
    planner._select(state, SimpleNamespace(selected_region_id=10))
    assert planner.phase == "select"


def test_window_positions_and_hides_chrome_for_source_templates(monkeypatch):
    calls = []
    flags = SimpleNamespace(no_scrollbar=1, no_scroll_with_mouse=2, no_title_bar=4)
    monkeypatch.setattr(strategic_planner, "imgui", SimpleNamespace(
        get_io=lambda: SimpleNamespace(display_size=SimpleNamespace(x=800, y=600)),
        WindowFlags_=flags,
    ))
    monkeypatch.setattr(
        strategic_planner.WindowManager,
        "window",
        lambda *args, **kwargs: calls.append((args, kwargs)) or "window-context",
    )
    planner = StrategicPlanner(object())

    assert planner._window("Strategic_Launch_Window", "Launch", "launch", (300, 200), at_bottom=True) == "window-context"
    assert planner._window("ordinary", "Ordinary", "ordinary", (200, 100)) == "window-context"
    assert calls[0][1]["x"] == 0
    assert calls[0][1]["y"] == 400
    assert calls[0][1]["flags"] == 7
    assert calls[1][1]["x"] == 300
    assert calls[1][1]["y"] == 250
    assert calls[1][1]["flags"] == 3


def test_country_phase_renders_controls_and_advances_to_launch(monkeypatch):
    fake = Imgui(combo_result=(False, 0))
    monkeypatch.setattr(strategic_planner, "imgui", fake)
    monkeypatch.setattr(strategic_planner, "GMLWidgets", lambda _root: Ui(clicked={
        "strategic.target.suggested", "strategic.target.prepare",
    }))
    planner = StrategicPlanner(SimpleNamespace(
        strategic_inventory_for_country=lambda *_args: [{"id": "W1"}],
        strategic_authorization_contexts=lambda *_args: ["regional"],
    ))
    planner.plan = StrategicPlan(country="USA", target_region=2, selected_weapons={"W1"})
    planner.plan.actions = lambda *_args, **_kwargs: ([], [])
    planner._window = _open_window()

    planner._country(
        state_with_regions([{"id": 2, "owner": "CAN", "name": "North"}]),
        SimpleNamespace(net_client=SimpleNamespace(player_id="player-1"), selected_region_id=2),
    )

    assert planner.phase == "launch"
    assert planner.plan.selected_weapons == {"W1"}
    assert "strategic.target.weapon" in [kwargs.get("test_id") for _, kwargs in fake.combos]


def test_country_phase_handles_empty_inventory_and_closed_or_returned_windows(monkeypatch):
    fake = Imgui()
    monkeypatch.setattr(strategic_planner, "imgui", fake)
    planner = StrategicPlanner(SimpleNamespace(
        strategic_inventory_for_country=lambda *_args: [],
        strategic_authorization_contexts=lambda *_args: [],
    ))
    planner.plan = StrategicPlan(country="USA")
    assert planner._render_weapon_selection(state_with_regions([]), Ui()) == []
    assert planner.plan.selected_weapons == set()

    planner._window = _open_window(False)
    planner.phase = "country"
    planner._country(state_with_regions([]), SimpleNamespace(net_client=None, selected_region_id=None))
    assert planner.phase == ""

    monkeypatch.setattr(strategic_planner, "GMLWidgets", lambda _root: Ui(clicked={"strategic.target.return"}))
    planner._window = _open_window()
    planner.phase = "country"
    planner._country(state_with_regions([]), SimpleNamespace(net_client=None, selected_region_id=None))
    assert planner.phase == ""


def test_multiple_phase_assigns_inventory_and_opens_missile_list(monkeypatch):
    fake = Imgui(checkbox_result=(True, True), combo_result=(False, 1))
    monkeypatch.setattr(strategic_planner, "imgui", fake)
    monkeypatch.setattr(strategic_planner.UIPrimitives, "fit_text", staticmethod(lambda value, _width: value))
    monkeypatch.setattr(strategic_planner, "GMLWidgets", lambda _root: Ui(clicked={
        "strategic.multiple.missiles", "strategic.multiple.prepare",
    }))
    monkeypatch.setattr(strategic_planner, "gml_child_frame", lambda *_args, **_kwargs: _open_window()())
    planner = StrategicPlanner(SimpleNamespace(strategic_inventory_for_country=lambda *_args: [
        {"id": "W1", "ready": 4},
    ]))
    planner.plan = StrategicPlan(country="USA", target_region=2)
    planner.plan.actions = lambda *_args, **_kwargs: ([], [])
    planner._window = _open_window()
    state = state_with_regions([
        {"id": 2, "owner": "CAN", "name": "North"},
        {"id": 3, "owner": "MEX", "name": "South"},
    ])

    planner._multiple(state, SimpleNamespace(net_client=SimpleNamespace(player_id="player-1")))

    assert planner.plan.selected_weapons == {"W1"}
    assert planner.plan.assignments == {"W1": 3}
    assert planner._missile_selection == {"W1"}
    assert planner.phase == "launch"

    planner._window = _open_window(False)
    planner.phase = "multiple"
    planner._multiple(state, SimpleNamespace(net_client=None))
    assert planner.phase == "country"
    assert planner.multiple is False


def test_assignment_row_removes_disabled_weapon_when_there_is_no_target(monkeypatch):
    fake = Imgui(checkbox_result=(True, False))
    monkeypatch.setattr(strategic_planner, "imgui", fake)
    monkeypatch.setattr(strategic_planner.UIPrimitives, "fit_text", staticmethod(lambda value, _width: value))
    planner = StrategicPlanner(object())
    planner.plan = StrategicPlan(country="USA", selected_weapons={"W1"})

    planner._render_assignment_row({"id": "W1"}, [])

    assert planner.plan.selected_weapons == set()
    assert planner.plan.assignments == {}


def test_missile_phase_selects_weapon_payload_and_transitions(monkeypatch):
    checkbox_answers = iter([(True, True), (True, False)])
    monkeypatch.setattr(strategic_planner, "imgui", SimpleNamespace(
        checkbox=lambda *_args, **_kwargs: next(checkbox_answers),
        same_line=lambda *_args: None,
        text=lambda *_args, **_kwargs: None,
    ))
    monkeypatch.setattr(strategic_planner.UIPrimitives, "fit_text", staticmethod(lambda value, _width: value))
    monkeypatch.setattr(strategic_planner, "resolve_region_name", lambda _state, region_id: f"Region {region_id}")
    monkeypatch.setattr(strategic_planner, "GMLWidgets", lambda _root: Ui(clicked={
        "strategic.missiles.all", "strategic.missiles.confirm",
    }))
    monkeypatch.setattr(strategic_planner, "gml_child_frame", lambda *_args, **_kwargs: _open_window()())
    planner = StrategicPlanner(SimpleNamespace(
        strategic_inventory_for_country=lambda *_args: [{
            "id": "W1", "ready": 2, "quantity": 3, "payload_level": 1, "origin_region_id": 4,
        }],
        strategic_payload_profiles=lambda *_args: {1: (100.0, 5.0)},
    ))
    planner.plan = StrategicPlan(country="USA", assignments={"W1": 9})
    planner._missile_selection = set()
    planner._window = _open_window()

    planner._missiles(state_with_regions([]), SimpleNamespace())

    assert planner.plan.selected_weapons == {"W1"}
    assert planner._missile_selection == {"W1"}
    assert planner.phase == "multiple"

    monkeypatch.setattr(strategic_planner, "GMLWidgets", lambda _root: Ui(clicked={
        "strategic.missiles.none", "strategic.missiles.confirm",
    }))
    planner.phase = "missiles"
    planner._missiles(state_with_regions([]), SimpleNamespace())
    assert planner.plan.selected_weapons == set()
    assert planner._missile_selection == set()

    planner._window = _open_window(False)
    planner.phase = "missiles"
    planner._missiles(state_with_regions([]), SimpleNamespace())
    assert planner.phase == "multiple"


def test_launch_phase_aborts_or_sends_the_complete_action_batch(monkeypatch):
    monkeypatch.setattr(strategic_planner, "GMLWidgets", lambda _root: Ui(clicked={"strategic.launch.abort"}))
    planner = StrategicPlanner(object())
    planner.plan = StrategicPlan(country="USA", selected_weapons={"W1"})
    planner.plan.actions = lambda *_args, **_kwargs: (["action"], [])
    planner.multiple = True
    planner._window = _open_window(False)
    context = SimpleNamespace(net_client=SimpleNamespace(player_id="player-1", send_action=lambda _action: None))

    planner._launch(state_with_regions([]), context)
    assert planner.phase == "multiple"

    planner._window = _open_window()
    planner.phase = "launch"
    planner._launch(state_with_regions([]), context)
    assert planner.phase == "multiple"

    sent = []
    context.net_client.send_action = sent.append
    monkeypatch.setattr(strategic_planner, "GMLWidgets", lambda _root: Ui(clicked={"strategic.launch.confirm"}))
    planner.multiple = False
    planner.plan.selected_weapons = {"W1"}
    planner._launch(state_with_regions([]), context)
    assert sent == ["action"]
    assert planner.plan.selected_weapons == set()
    assert planner.phase == "country"
