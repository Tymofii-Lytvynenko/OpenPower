"""Export every extracted REFERENCE GML template as Python layout-reference data."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from utils.reference_paths import resolve_reference_file


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "docs" / "ui" / "reference" / "window_registry.csv"
DEFAULT_COMPONENTS = ROOT / "docs" / "ui" / "reference" / "component_tree.csv"
DEFAULT_OUTPUT = ROOT / "src" / "client" / "ui" / "layouts" / "gml_layouts.json"
DEFAULT_ROWS_OUTPUT = ROOT / "src" / "client" / "ui" / "layouts" / "gml_rows.json"
SUPPORTED_DYNAMIC_ROWS = (
    "lstInternalLawsGroups",
    "lstInternalLawsLawsItem",
    "lstCovertActionsItem",
    "lstTreatyEligibleCountryItem",
    "lstMailItem",
    "lstUnitDeployItem",
    "lstUnitProductionItem",
    "lstThematicLegendItem",
)
def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def _integer(value: str | None, default: int = 0) -> int:
    if value is None or value.strip() == "":
        return default
    return int(float(value))


def _optional_integer(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    return _integer(value)


def _resolve_catalog_path(catalog_path: Path) -> Path:
    if catalog_path.is_file():
        return catalog_path
    return resolve_reference_file(ROOT, catalog_path.relative_to(ROOT))


def _source_text_metadata(catalog_path):
    catalog_path = _resolve_catalog_path(catalog_path)
    if not catalog_path.exists():
        return {}
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))["templates"]
    result = {}
    def visit(node, parent=""):
        path = parent + "/" + node["name"] if parent else node["name"]
        properties = node["properties"]
        metadata = {
            "text_offset": [float(v.strip()) for v in properties.get("TextOffset", "0, 0").split(",")],
            "text_align": properties.get("TextAlign", ""),
        }
        if node.get("type") == "g_def_tabbd":
            tab_names = [
                name.strip()
                for name in properties.get("TabNames", "").split(",")
                if name.strip() and name.strip() != "0"
            ]
            metadata["tab_layout"] = {
                "button_type": properties.get("ButtonType", ""),
                "button_width": _integer(properties.get("ButtonsWidth")),
                "button_height": _integer(properties.get("ButtonsHeight")),
                "button_distance": _integer(properties.get("ButtonsDistance")),
                "button_offset_left": _integer(properties.get("ButtonsOffsetLeft")),
                "frame_offset_top": _integer(properties.get("FrameOffsetTop")),
                "active_tab": _integer(properties.get("ActiveTab")),
                "tab_names": tab_names,
            }
        font_size = properties.get("FontSize", "").strip()
        if font_size:
            metadata["font_size"] = float(font_size)
        result[path] = metadata
        for child in node["children"]:
            visit(child, path)
    # These source metrics stay passive until a Python widget explicitly binds to a GML slot.
    for node in catalog.values():
        visit(node)
    return result


def _component_template_sizes(catalog_path):
    catalog_path = _resolve_catalog_path(catalog_path)
    if not catalog_path.exists():
        return {}
    templates = json.loads(catalog_path.read_text(encoding="utf-8"))["templates"]
    return {
        name: {
            "width": _integer(node["properties"].get("Width")),
            "height": _integer(node["properties"].get("Height")),
        }
        for name, node in templates.items()
        if node.get("properties", {}).get("Width", "").strip()
        and node.get("properties", {}).get("Height", "").strip()
    }


def export_layouts(registry_path: Path, component_path: Path, catalog_path: Path = ROOT / ".codex/reference_ui_catalog.json") -> dict:
    catalog_path = _resolve_catalog_path(catalog_path)
    text_metadata = _source_text_metadata(catalog_path)
    registry_rows = _read_csv(registry_path)
    registry_by_window = {
        row["window_id"]: row
        for row in registry_rows
        if row.get("gml_template", "").strip()
    }
    components_by_window: dict[str, list[dict[str, str]]] = {}
    for component in _read_csv(component_path):
        components_by_window.setdefault(component["window_id"], []).append(component)

    ordered_windows = [row["window_id"] for row in registry_rows if row.get("gml_template", "").strip()]
    ordered_windows.extend(sorted(set(components_by_window) - set(ordered_windows)))

    result = {
        "source": "docs/ui/reference/window_registry.csv and component_tree.csv",
        "reference_viewport": [1280, 720],
        "component_template_sizes": _component_template_sizes(catalog_path),
        "windows": {},
    }
    for window_id in ordered_windows:
        rows = components_by_window.get(window_id, [])
        root = next((row for row in rows if row["component_path"] == window_id), None)
        if root is None:
            continue
        window = registry_by_window.get(window_id, {})
        template = window.get("gml_template") or window_id
        width = _integer(window.get("width")) or _integer(root.get("width"))
        height = _integer(window.get("height")) or _integer(root.get("height"))
        if width <= 0 or height <= 0:
            continue
        resolved: dict[str, dict] = {}
        pending = list(rows)
        while pending:
            remaining = []
            for row in pending:
                path = row["component_path"]
                parent_path = row["parent_path"]
                parent = resolved.get(parent_path)
                if parent_path and parent is None:
                    remaining.append(row)
                    continue

                local_x = _integer(row["left"])
                local_y = _integer(row["top"])
                parent_x = parent["rect"]["x"] if parent else 0
                parent_y = parent["rect"]["y"] if parent else 0
                item = {
                    "path": path,
                    "id": row["component_id"],
                    "type": row["type"],
                    "kind": row["kind"],
                    "parent": parent_path,
                    "order": _integer(row["sibling_order"]),
                    "sequence": len(resolved),
                    "z_order": _optional_integer(row["z_order"]),
                    "rect": {
                        "x": parent_x + local_x,
                        "y": parent_y + local_y,
                        "width": _integer(row["width"]),
                        "height": _integer(row["height"]),
                    },
                    "local_rect": {
                        "x": local_x,
                        "y": local_y,
                        "width": _integer(row["width"]),
                        "height": _integer(row["height"]),
                    },
                    "anchor": row["anchor"],
                    "text_token": row["text_token"],
                    "tooltip_token": row["tooltip_token"],
                    "enabled": row["gml_enabled"].lower() not in {"false", "0", "no"},
                    "visible": row["gml_visible"].lower() not in {"false", "0", "no"},
                    "status": row["status"],
                }
                item.update(text_metadata.get(path, {}))
                resolved[path] = item
            if len(remaining) == len(pending):
                unresolved = ", ".join(row["component_path"] for row in remaining[:5])
                raise ValueError(f"Unresolved component parents in {window_id}: {unresolved}")
            pending = remaining

        result["windows"][window_id] = {
            "template": template,
            "width": width,
            "height": height,
            "sections": [section for section in window.get("sections", "").split(";") if section],
            "components": list(resolved.values()),
        }
    return result


def export_row_templates(catalog_path: Path = ROOT / ".codex/reference_ui_catalog.json") -> dict:
    """Export source row templates used by repeatable OpenPower lists."""
    catalog_path = _resolve_catalog_path(catalog_path)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))["templates"]
    missing = set(SUPPORTED_DYNAMIC_ROWS) - catalog.keys()
    if missing:
        raise ValueError(f"Missing GML row templates: {', '.join(sorted(missing))}")
    return {name: catalog[name] for name in SUPPORTED_DYNAMIC_ROWS}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--components", type=Path, default=DEFAULT_COMPONENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--rows-output", type=Path, default=DEFAULT_ROWS_OUTPUT)
    args = parser.parse_args()

    payload = export_layouts(args.registry, args.components)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    rows = export_row_templates()
    args.rows_output.parent.mkdir(parents=True, exist_ok=True)
    args.rows_output.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Exported {} extracted GML layouts to {}".format(
        len(payload["windows"]), args.output
    ))
    print("Exported {} dynamic GML row templates to {}".format(
        len(rows), args.rows_output
    ))


if __name__ == "__main__":
    main()
