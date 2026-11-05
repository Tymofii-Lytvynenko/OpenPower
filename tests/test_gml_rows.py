import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.client.ui.layouts.gml_rows import row_layout
from src.client.ui.layouts.gml_layout import GMLLayoutSession
from utils.export_gml_ui_rows import export_rows
from utils.reference_paths import resolve_reference_file

ROOT = Path(__file__).resolve().parents[1]


def test_exported_rows_match_resolved_reference_catalog():
    catalog_path = resolve_reference_file(ROOT, ".codex/reference_ui_catalog.json")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    actual = json.loads((ROOT / "src/client/ui/layouts/gml_rows.json").read_text(encoding="utf-8"))
    assert actual == export_rows(catalog)
    expected_sizes = {
        "lstGoalItem": (435, 16),
        "lstCovertActionsItem": (681, 16),
        "lstTreatyEligibleCountryItem": (251, 17),
        "lstMailItem": (460, 18),
        "lstInternalLawsGroups": (328, 16),
        "lstInternalLawsLawsItem": (328, 16),
        "lstUnitDeployItem": (437, 18),
        "lstUnitProductionItem": (522, 18),
        "lstThematicLegendItem": (121, 15),
    }
    for name in actual:
        layout = row_layout(name)
        assert (layout.width, layout.height) == expected_sizes[name]

        def visit(children, parent):
            for child in children:
                path = f"{parent}/{child['name']}"
                yield path, child
                yield from visit(child.get("children", []), path)

        source_components = dict(visit(actual[name]["children"], name))
        assert {component.path for component in layout.components} == set(source_components)
        for component in layout.components:
            child = source_components[component.path]
            p = child["properties"]
            assert (component.rect.x, component.rect.y, component.rect.width, component.rect.height) == tuple(float(p[k]) for k in ["Left", "Top", "Width", "Height"])
            assert component.anchor == p.get("Anchor", "")
            assert component.text_align == p.get("TextAlign", "")
            assert component.text_offset == tuple(float(value.strip()) for value in p.get("TextOffset", "0, 0").split(","))
            assert component.font_size == (float(p["FontSize"]) if p.get("FontSize") else None)


def test_percentage_text_offset_prevents_overlap_with_source_status_slot():
    layout = row_layout("lstInternalLawsGroups")
    label = layout.component("lblPerc")
    combo = layout.component("cboStatus")
    assert label.rect.x + label.rect.width > combo.rect.x
    assert label.rect.x + label.rect.width + label.text_offset[0] <= combo.rect.x
    native = MagicMock()
    native.get_scroll_x.return_value = 0
    native.get_font_size.return_value = 12
    native.get_scroll_y.return_value = 32
    native.calc_text_size.return_value = SimpleNamespace(x=30.)
    session = GMLLayoutSession(layout, (100, 232), (328, 16))
    with patch("src.client.ui.core.instrumented_imgui.imgui", native):
        session.place_widget("text", ("72.0%",), explicit_id=label.path, align="right")
    native.set_cursor_screen_pos.assert_called_once_with((296., 202.))


def test_repeated_row_can_scale_into_a_narrow_parent():
    layout = row_layout("lstUnitProductionItem")
    session = GMLLayoutSession(layout, (0, 0), (layout.width, layout.height))
    session.scale_subtree_x(layout.template, 0.95)

    priority = session.rect_for("lstUnitProductionItem/cboPriority")
    assert priority.x + priority.width <= layout.width * 0.95
