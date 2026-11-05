"""Validate resolved GML catalog structure against local source."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator


def _walk(template: str, node: dict[str, Any], parent: str = "", order: int = 0) -> Iterator[dict[str, Any]]:
    path = f"{parent}/{node['name']}" if parent else node["name"]
    yield {"template": template, "path": path, "parent": parent, "order": order, "node": node}
    for child_order, child in enumerate(node.get("children", [])):
        yield from _walk(template, child, path, child_order)


def _validate_gml(source_path: Path, catalog: dict[str, Any]) -> dict[str, Any]:
    root = ET.fromstring(source_path.read_bytes())
    definitions = root.findall("OBJECT")
    names = []
    for definition in definitions:
        name = definition.findtext("NAME", default="").strip()
        if name:
            names.append(name)
    raw_object_count = sum(1 for element in root.iter("OBJECT"))
    catalog_names = set(catalog["templates"])
    unknown_roots = sorted(set(names) ^ catalog_names)
    resolved_count = sum(1 for template, tree in catalog["templates"].items() for _ in _walk(template, tree))
    base_names = set((catalog.get("meta") or {}).get("root_base_counts", {}))
    base_names.update(
        element.text.strip()
        for element in root.iter("BASE")
        if element.text and element.text.strip()
    )
    base_names.update({"frmBaseWindow"})
    unknown_types: set[str] = set()
    references: dict[str, set[str]] = defaultdict(set)
    for obj in root.iter("OBJECT"):
        direct_name = obj.findtext("NAME", default="").strip()
        for tag in ("BASE", "TYPE"):
            value = obj.findtext(tag, default="").strip()
            if not value:
                continue
            if value not in catalog_names and value not in base_names and not value.startswith("g_def_"):
                unknown_types.add(value)
            if obj in definitions and direct_name and value in catalog_names:
                references[direct_name].add(value)

    cycles: list[list[str]] = []
    active: list[str] = []
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in active:
            cycles.append(active[active.index(name):] + [name])
            return
        if name in visited:
            return
        active.append(name)
        for dependency in sorted(references.get(name, set())):
            visit(dependency)
        active.pop()
        visited.add(name)

    for name in names:
        visit(name)
    return {
        "definition_count": len(definitions),
        "root_object_count": len(names),
        "raw_object_count": raw_object_count,
        "resolved_catalog_node_count": resolved_count,
        "unknown_root_names": unknown_roots,
        "unknown_gml_types": sorted(unknown_types),
        "inheritance_cycles": cycles,
    }


