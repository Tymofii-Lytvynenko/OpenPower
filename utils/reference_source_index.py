"""Index local reference source declarations and window spawn calls."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from utils.reference_cpp_parser import cpp_functions, find_matching as _find_matching, mask_cpp_noncode


def _source_index(source_dir: Path) -> dict[str, Any]:
    files = sorted(source_dir.glob("*.cpp"))
    texts = {path: path.read_text(encoding="utf-8", errors="replace") for path in files}
    header_texts = {
        path: path.read_text(encoding="utf-8", errors="replace")
        for path in sorted((source_dir.parent / "Include").glob("*.h"))
    }
    base_classes: dict[str, set[str]] = defaultdict(set)
    for header_text in header_texts.values():
        clean_header = re.sub(r"/\*.*?\*/|//[^\n]*", "", header_text, flags=re.S)
        for class_name in re.findall(r"\bclass\s+(\w+)\s*:", clean_header):
            declaration = re.search(
                rf"\bclass\s+{re.escape(class_name)}\s*:\s*(.*?)(?:\{{|;)",
                clean_header,
                re.S,
            )
            if declaration is None:
                continue
            for base_spec in declaration.group(1).split(","):
                identifiers = re.findall(r"[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*", base_spec)
                if identifiers:
                    base_classes[class_name].add(identifiers[-1].split("::")[-1])
    type_rows: list[dict[str, Any]] = []
    for path, text in texts.items():
        type_name_pattern = re.compile(
            r'const\s+GString\s+(\w+)::TypeName\s*(?:'
            r'\(\s*L"([^"]+)"\s*\)|=\s*L"([^"]+)"'
            r')'
        )
        for match in type_name_pattern.finditer(text):
            template = match.group(2) or match.group(3)
            type_rows.append({
                "class": match.group(1), "template": template,
                "file": path.name, "line": text.count("\n", 0, match.start()) + 1,
            })
    type_by_class = {row["class"]: row for row in type_rows}
    type_by_template = {row["template"]: row for row in type_rows}

    layer_path = next(
        (path for path in files if path.name.endswith("data_display_layer.cpp")),
        None,
    )
    layer_text = texts.get(layer_path, "")
    uncommented_layer = re.sub(r"/\*.*?\*/|//[^\n]*", "", layer_text, flags=re.S)
    registered_classes = set(re.findall(r"REGISTER_GUI_OBJECT\s*\(\s*(\w+)\s*\)", uncommented_layer))
    spawn_templates: dict[str, str] = {}
    for match in re.finditer(r"\bbool\s+GDataDisplayLayer::(\w+Spawn)\s*\([^)]*\)\s*\{", layer_text):
        body_start = layer_text.find("{", match.start())
        body_end = _find_matching(layer_text, body_start, "{", "}")
        if body_end < 0:
            continue
        body = layer_text[body_start + 1:body_end]
        type_match = re.search(r"(\w+)::TypeName", body)
        if type_match and type_match.group(1) in type_by_class:
            spawn_templates[match.group(1)] = type_by_class[type_match.group(1)]["template"]

    non_gml_spawn_targets: dict[str, str] = {}
    for path, text in texts.items():
        for function in cpp_functions(text):
            method = function["method"]
            if not method.endswith("WindowSpawn") or method in spawn_templates:
                continue
            object_match = re.search(
                r"CREATE_GUI_OBJECT\w*\s*\(\s*(?:GUI::)?(\w+)",
                function["body"],
            )
            if object_match:
                class_name = object_match.group(1)
                type_row = type_by_class.get(class_name)
                if type_row:
                    spawn_templates[method] = type_row["template"]
                else:
                    target = f"non-GML/{class_name}"
                    spawn_templates[method] = target
                    non_gml_spawn_targets[method] = target

    spawn_calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_code = "\n".join(re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S) for text in texts.values())
    for path, text in texts.items():
        # Preserve locations and exclude strings, which can contain comment markers or example calls.
        clean = mask_cpp_noncode(text)
        for match in re.finditer(r"g_ClientDDL\.(\w+Spawn)\s*\(", clean):
            method = match.group(1)
            spawn_calls[method].append({
                "file": path.name,
                "line": clean.count("\n", 0, match.start()) + 1,
                "target": spawn_templates.get(method, ""),
            })
    return {
        "files": files,
        "texts": texts,
        "type_rows": type_rows,
        "type_by_class": type_by_class,
        "type_by_template": type_by_template,
        "base_classes": base_classes,
        "registered_classes": registered_classes,
        "spawn_templates": spawn_templates,
        "non_gml_spawn_targets": non_gml_spawn_targets,
        "spawn_calls": spawn_calls,
        "all_code": all_code,
    }


