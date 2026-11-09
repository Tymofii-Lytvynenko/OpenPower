from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

import src.client.ui.components.project_credits_content as credits_module
from src.client.ui.components.project_credits_content import (
    ProjectCredits,
    ProjectCreditsContent,
    load_project_credits,
)
from src.client.ui.components.reference_credit_roster import REFERENCE_STEAM_CREDIT_GROUPS


def _component(component_id, *, x=0.0, y=0.0, width=100.0, height=20.0, path=None):
    return SimpleNamespace(
        component_id=component_id,
        path=path or f"Credits_Window/frmInner/frmCredits/frmInner/{component_id}",
        local_rect=SimpleNamespace(x=x, y=y, width=width, height=height),
        font_size=0.0,
        text_align="TopLeft",
        text_offset=(0.0, 0.0),
    )


def _source_layout(*, include_people=True):
    lookup = {}
    components = []
    direct_ids = (
        *ProjectCreditsContent._GOLEMLABS_ROLE_SLOTS,
        *ProjectCreditsContent._NORDIC_ROLE_SLOTS,
        *ProjectCreditsContent._NORDIC_PEOPLE_SLOTS,
        "lblTitle", "lblTitle5", "lblNordicGames", "lblTitle9", "lblTitle35", "lblTitle91",
    )
    for component_id in direct_ids:
        component = _component(component_id)
        lookup[component_id] = component

    groups = {group.id: group for group in REFERENCE_STEAM_CREDIT_GROUPS}
    dynamic_slots = (
        ("golemlabs", "golem-person", 250.0, 150.0, 38.0),
        ("dreamcatcher", "dream-role", 0.0, 249.0, 636.0),
        ("dreamcatcher", "dream-person", 250.0, 150.0, 636.0),
    )
    for group_id, prefix, x, width, start_y in dynamic_slots:
        if not include_people:
            continue
        group = groups[group_id]
        count = (
            sum(len(entry.people) for entry in group.entries)
            if "person" in prefix
            else len(group.entries)
        )
        for index in range(count):
            component_id = f"lblTitle{prefix}{index}"
            component = _component(
                component_id,
                x=x,
                y=start_y + index,
                width=width,
            )
            components.append(component)
            lookup[component_id] = component

    if include_people:
        excluded = _component("lblTitle35", x=250.0, y=500.0, width=150.0)
        components.append(excluded)
        lookup["lblTitle35"] = excluded

    class Layout:
        def __init__(self):
            self.components = components

        def component(self, path):
            return lookup.get(path.rsplit("/", 1)[-1])

    return Layout()


def test_load_project_credits_reads_metadata_and_handles_missing_distribution(monkeypatch):
    project = Mock()
    project.get_all.return_value = ["Author One", "Author Two"]
    values = {"Version": "2.3.4", "License": "\n# MIT License\nAdditional terms"}
    project.get.side_effect = lambda key, default="": values.get(key, default)
    monkeypatch.setattr(credits_module, "metadata", Mock(return_value=project))

    assert load_project_credits() == ProjectCredits(
        "OpenPower Engine", "2.3.4", ("Author One", "Author Two"), "MIT License",
    )

    monkeypatch.setattr(
        credits_module,
        "metadata",
        Mock(side_effect=credits_module.PackageNotFoundError),
    )
    assert load_project_credits() == ProjectCredits("OpenPower Engine", "", (), "")


def test_constructor_loads_default_metadata_and_builds_source_slots(monkeypatch):
    credits = ProjectCredits("OpenPower Engine", "2.0", (), "MIT")
    load_credits = Mock(return_value=credits)
    layout = _source_layout()
    get_layout = Mock(return_value=layout)
    monkeypatch.setattr(credits_module, "load_project_credits", load_credits)
    monkeypatch.setattr(credits_module, "get_gml_layout", get_layout)

    content = ProjectCreditsContent()

    assert content._credits is credits
    assert content._layout is layout
    assert set(content._slots) == {group.id for group in REFERENCE_STEAM_CREDIT_GROUPS}
    load_credits.assert_called_once_with()
    get_layout.assert_called_once_with("Credits_Window")

    supplied = ProjectCredits("Other", "1", (), "")
    second = ProjectCreditsContent(supplied)
    assert second._credits is supplied
    load_credits.assert_called_once_with()
    get_layout.assert_called_with("Credits_Window")


def test_push_font_size_uses_scaled_font_and_clamps_zero_scale(monkeypatch):
    imgui = Mock()
    imgui.get_style.return_value = SimpleNamespace(font_scale_main=2.0, font_scale_dpi=1.5)
    monkeypatch.setattr(credits_module, "imgui", imgui)

    ProjectCreditsContent._push_font_size(12.0)
    imgui.push_font.assert_called_once_with(None, 4.0)

    imgui.get_style.return_value = SimpleNamespace(font_scale_main=0.0, font_scale_dpi=1.0)
    ProjectCreditsContent._push_font_size(12.0)
    assert imgui.push_font.call_args == ((None, 120.0), {})


def test_component_lookup_and_column_filtering_sort_by_source_y():
    content = object.__new__(ProjectCreditsContent)
    first = _component("lblTitleA", x=250.0, y=80.0, width=150.0)
    second = _component("lblTitleB", x=250.0, y=40.0, width=150.0)
    excluded = _component("lblTitleExcluded", x=250.0, y=60.0, width=150.0)
    wrong_column = _component("lblTitleWrong", x=0.0, y=50.0, width=150.0)
    wrong_path = _component("lblTitleOther", x=250.0, y=50.0, width=150.0, path="Other/label")
    content._layout = SimpleNamespace(components=[first, second, excluded, wrong_column, wrong_path])

    assert content._column_slots(
        x=250.0, width=150.0, minimum_y=38.0, maximum_y=100.0,
        excluded={"lblTitleExcluded"},
    ) == (second, first)

    content._layout = SimpleNamespace(component=lambda _path: None)
    with pytest.raises(RuntimeError, match="Missing GML credits slot"):
        content._component("lblTitle")


def test_build_source_slots_matches_roster_and_rejects_slot_mismatch():
    content = object.__new__(ProjectCreditsContent)
    content._layout = _source_layout()
    slots = content._build_source_slots()
    groups = {group.id: group for group in REFERENCE_STEAM_CREDIT_GROUPS}

    for group_id, group in groups.items():
        roles, people = slots[group_id]
        assert len(roles) == len(group.entries)
        assert len(people) == sum(len(entry.people) for entry in group.entries)

    content._layout = _source_layout(include_people=False)
    with pytest.raises(RuntimeError, match="GML credits slot mismatch for golemlabs"):
        content._build_source_slots()


def test_runtime_rect_applies_source_window_shift_only_to_lower_title_rows():
    content = object.__new__(ProjectCreditsContent)
    lower_title = _component("lblTitle91", x=3.0, y=700.0, width=80.0, height=12.0)
    ordinary_title = _component("lblTitle", x=3.0, y=600.0, width=80.0, height=12.0)
    unrelated = _component("lblBody", x=3.0, y=700.0, width=80.0, height=12.0)

    assert content._runtime_rect(lower_title).y == 840.0
    assert content._runtime_rect(ordinary_title) is ordinary_title.local_rect
    assert content._runtime_rect(unrelated) is unrelated.local_rect


def test_render_source_label_aligns_text_and_restores_font_and_clip(monkeypatch):
    imgui = Mock()
    imgui.get_style.return_value = SimpleNamespace(font_scale_main=2.0, font_scale_dpi=1.0)
    imgui.calc_text_size.return_value = SimpleNamespace(x=40.0, y=10.0)
    imgui.get_window_pos.return_value = SimpleNamespace(x=100.0, y=200.0)
    imgui.get_scroll_x.return_value = 5.0
    imgui.get_scroll_y.return_value = 7.0
    monkeypatch.setattr(credits_module, "imgui", imgui)
    content = object.__new__(ProjectCreditsContent)
    component = _component("lblTitle", x=10.0, y=20.0, width=100.0, height=30.0)
    component.font_size = 20.0
    component.text_align = "MiddleRight"
    component.text_offset = (2.0, 3.0)

    assert content._render_source_label(component, "credit", fallback_font_size=9.0, test_id="credit.name") == 40.0

    imgui.push_font.assert_called_once_with(None, 10.0)
    imgui.set_cursor_pos.assert_called_once_with((72.0, 33.0))
    imgui.push_clip_rect.assert_called_once_with((105.0, 213.0), (205.0, 243.0), True)
    imgui.text.assert_called_once_with("credit", test_id="credit.name")
    imgui.pop_clip_rect.assert_called_once_with()
    imgui.pop_font.assert_called_once_with()


def test_render_source_label_centers_text_and_uses_fallback_font_size(monkeypatch):
    imgui = Mock()
    imgui.get_style.return_value = SimpleNamespace(font_scale_main=1.0, font_scale_dpi=1.0)
    imgui.calc_text_size.return_value = SimpleNamespace(x=20.0, y=10.0)
    imgui.get_window_pos.return_value = SimpleNamespace(x=0.0, y=0.0)
    imgui.get_scroll_x.return_value = 0.0
    imgui.get_scroll_y.return_value = 0.0
    monkeypatch.setattr(credits_module, "imgui", imgui)
    content = object.__new__(ProjectCreditsContent)
    component = _component("lblTitle", x=10.0, y=20.0, width=100.0, height=30.0)
    component.text_align = "MiddleCenter"
    component.text_offset = (0.0, 0.0)

    content._render_source_label(component, "credit", fallback_font_size=12.0)

    imgui.push_font.assert_called_once_with(None, 12.0)
    imgui.set_cursor_pos.assert_called_once_with((50.0, 30.0))


def test_render_emits_roster_and_project_metadata_with_overflow_tooltips(monkeypatch):
    imgui = Mock()
    imgui.is_item_hovered.return_value = True
    monkeypatch.setattr(credits_module, "imgui", imgui)
    content = object.__new__(ProjectCreditsContent)
    content._credits = ProjectCredits("OpenPower Engine", "1.2.0", ("Author A", "Author B"), "MIT")
    content._component = Mock(side_effect=lambda name: _component(name))
    content._render_source_label = Mock(return_value=200.0)
    content._slots = {}
    for group in REFERENCE_STEAM_CREDIT_GROUPS:
        role_slots = tuple(_component(f"role-{group.id}-{index}") for index, _ in enumerate(group.entries))
        people_slots = tuple(
            _component(f"person-{group.id}-{index}", width=100.0)
            for index in range(sum(len(entry.people) for entry in group.entries))
        )
        for slot in people_slots:
            slot.text_offset = (0.0, 0.0)
        content._slots[group.id] = (role_slots, people_slots)

    content.render("credits")

    assert any(call.args == ("Version: 1.2.0",) for call in imgui.text.call_args_list)
    assert imgui.bullet_text.call_args_list == [call("Author A"), call("Author B")]
    assert any(call.args[0] == "MIT" for call in imgui.text_wrapped.call_args_list)
    assert imgui.set_tooltip.call_count >= 2
    rendered_test_ids = [call.kwargs.get("test_id", "") for call in content._render_source_label.call_args_list]
    assert any(".person." in test_id for test_id in rendered_test_ids)
    assert any(test_id.endswith(".people") for test_id in rendered_test_ids)
    assert any(test_id.endswith("music_contact") for test_id in rendered_test_ids)
    assert any(test_id.endswith("copyright") for test_id in rendered_test_ids)


def test_render_shows_metadata_unavailable_fallback_without_tooltips(monkeypatch):
    imgui = Mock()
    imgui.is_item_hovered.return_value = False
    monkeypatch.setattr(credits_module, "imgui", imgui)
    content = object.__new__(ProjectCreditsContent)
    content._credits = ProjectCredits("OpenPower Engine", "", (), "")
    content._component = Mock(side_effect=lambda name: _component(name))
    content._render_source_label = Mock(return_value=10.0)
    content._slots = {
        group.id: (
            tuple(_component(f"role-{group.id}-{index}") for index, _ in enumerate(group.entries)),
            tuple(
                _component(f"person-{group.id}-{index}")
                for index in range(sum(len(entry.people) for entry in group.entries))
            ),
        )
        for group in REFERENCE_STEAM_CREDIT_GROUPS
    }

    content.render()

    imgui.text_wrapped.assert_called_once_with(
        "Project attribution metadata is unavailable.",
        test_id="project_credits.openpower.license",
    )
    imgui.bullet_text.assert_not_called()
    imgui.set_tooltip.assert_not_called()
