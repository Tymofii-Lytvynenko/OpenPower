"""Opt-in observability facade; native behavior is unchanged outside telemetry frames."""
from __future__ import annotations

import ast
import inspect
import math
from pathlib import Path
from functools import wraps, lru_cache

from imgui_bundle import imgui as native_imgui

from src.client.ui.core.testability import Rect, active_telemetry

_INTERACTIVE = {
    "button", "small_button", "invisible_button", "arrow_button", "color_button",
    "checkbox", "checkbox_flags", "radio_button", "selectable", "menu_item",
    "combo", "list_box", "color_edit3", "color_edit4", "color_picker3", "color_picker4",
    "tree_node", "tree_node_ex", "collapsing_header",
}
_DISPLAY = {
    "text", "text_unformatted", "text_colored", "text_disabled", "text_wrapped",
    "bullet_text", "label_text", "progress_bar", "image", "dummy", "separator",
    "separator_text", "bullet",
}
_CONTAINERS = {
    "begin": ("end", True, "window"),
    "begin_child": ("end_child", True, "child"),
    "begin_popup": ("end_popup", False, "popup"),
    "begin_popup_modal": ("end_popup", False, "popup"),
    "begin_popup_context_window": ("end_popup", False, "popup"),
    "begin_popup_context_item": ("end_popup", False, "popup"),
    "begin_tooltip": ("end_tooltip", True, "tooltip"),
    "begin_main_menu_bar": ("end_main_menu_bar", False, "menu_bar"),
    "begin_menu_bar": ("end_menu_bar", False, "menu_bar"),
    "begin_menu": ("end_menu", False, "menu"),
    "begin_combo": ("end_combo", False, "combo"),
    "begin_tab_bar": ("end_tab_bar", False, "tab_bar"),
    "begin_tab_item": ("end_tab_item", False, "tab"),
    "begin_table": ("end_table", False, "table"),
    "begin_group": ("end_group", True, "group"),
}
_WINDOW_KINDS = {"window", "child", "popup", "tooltip", "combo", "menu", "menu_bar"}
_END = {entry[0] for entry in _CONTAINERS.values()}
_VECTORS = {f"{api}{count}": count for api in ("input_int", "input_float", "slider_int", "slider_float", "drag_int", "drag_float") for count in (2, 3, 4)}


@lru_cache(maxsize=512)
def _source_path(filename: str) -> str:
    path = Path(filename)
    parts = path.parts
    if "src" in parts:
        path = Path(*parts[parts.index("src"):])
    return path.as_posix()


def _source(frame) -> dict[str, object]:
    return {"path": _source_path(frame.f_code.co_filename), "line": frame.f_lineno, "function": frame.f_code.co_name}


@lru_cache(maxsize=256)
def _sites(filename: str) -> dict[tuple[int, str], str]:
    """Use call order within each function so blank lines do not change IDs."""
    tree = ast.parse(Path(filename).read_text(encoding="utf-8-sig"))
    sites = {}
    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.scope = []
            self.counts = {}

        def visit_ClassDef(self, node):
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node):
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            if isinstance(node.func, ast.Attribute):
                api = node.func.attr
                scope = ".".join(self.scope)
                key = (scope, api)
                ordinal = self.counts.get(key, 0)
                self.counts[key] = ordinal + 1
                token = f"{scope}/{api}.{ordinal}"
                for line in range(node.lineno, node.end_lineno + 1):
                    sites[(line, api)] = token
            self.generic_visit(node)
    Visitor().visit(tree)
    return sites


def _site_id(source: dict, name: str) -> str:
    return _cached_site_id(source["path"], source["line"], name)


@lru_cache(maxsize=8192)
def _cached_site_id(path: str, line: int, name: str) -> str:
    try:
        token = _sites(str(Path(path).resolve())).get((line, name))
    except (OSError, SyntaxError):
        token = None
    # Resolving a path invokes Windows filesystem APIs; doing that for every
    # widget in every frame dominated telemetry-enabled client rendering.
    return f"{path}/{token or str(line) + '/' + name}"


def _label(name, args, kwargs) -> str:
    index = 1 if name == "text_colored" else 0
    if len(args) > index and isinstance(args[index], str):
        return args[index]
    return str(kwargs.get("label", kwargs.get("name", kwargs.get("str_id", name))))


def _rect(minimum, maximum) -> Rect:
    return Rect(float(minimum.x), float(minimum.y),
                float(maximum.x - minimum.x), float(maximum.y - minimum.y))


def _record_item(recorder, name, label, source, result, explicit_id=None, component_width=None, native=None, options=None):
    native = native or native_imgui
    native_id = int(native.get_item_id())
    if not native_id and name in {"input_int", "input_float", "input_double"}:
        # Scalar inputs with +/- steppers finish with a zero-ID group. Their
        # text field keeps the label ID under the temporary native ID scope.
        native_id = int(native.get_id(label))
    interactive = name in _INTERACTIVE or name.startswith(("input_", "slider_", "drag_", "v_slider_")) or name in {"begin_combo", "begin_menu", "begin_tab_item"}
    instance = "/".join(recorder._id_stack)
    label_key = label.split("##", 1)[1].lstrip("#") if "##" in label else ""
    base = f"auto/{recorder.parent_id or 'root'}/{_site_id(source, name)}"
    if instance or label_key:
        base += f"/{instance}/{label_key}"
    test_id = explicit_id or recorder.unique_id(base)
    value = result[1] if isinstance(result, tuple) and len(result) > 1 else None
    if not isinstance(value, (str, int, float, bool, list, tuple, type(None))):
        value = str(value)
    recorder.record_widget(
        test_id, label.split("##", 1)[0], name,
        bool(native.is_item_visible()), recorder.enabled,
        _rect(native.get_item_rect_min(), native.get_item_rect_max()),
        native_id, source=source, interactive=interactive, value=value,
    )
    if options is not None:
        recorder.set_options(test_id, options)
    if name in _VECTORS and component_width is not None:
        count = _VECTORS[name]
        p = native.get_item_rect_min()
        height = native.get_item_rect_max().y - p.y
        spacing = native.get_style().item_inner_spacing.x
        width = math.floor((component_width - spacing * (count - 1)) / count)
        components = []
        native.push_id(label)
        try:
            for index in range(count):
                native.push_id(index)
                try:
                    component_id = int(native.get_id(""))
                finally:
                    native.pop_id()
                components.append({"index": index, "imgui_id": component_id,
                                   "rect": Rect(p.x + index * (width + spacing), p.y, width, height).to_dict()})
        finally:
            native.pop_id()
        recorder.set_components(test_id, components)


class ImGuiFacade:
    """Compose native ImGui with automatic widget and container instrumentation."""

    def __init__(self, native=native_imgui):
        self._native = native
        self._wrappers = {}

    def __getattr__(self, name):
        target = getattr(self._native, name)
        observed = (name in _INTERACTIVE or name in _DISPLAY or name in _CONTAINERS
                    or name in _END or name in {"begin_disabled", "end_disabled", "get_window_draw_list", "push_id", "pop_id"}
                    or name.startswith(("input_", "slider_", "drag_", "v_slider_")))
        if not callable(target) or inspect.isclass(target):
            return target
        if name not in self._wrappers:
            @wraps(target)
            def call(*args, **kwargs):
                # Resolve the function at call time so patched native bindings
                # cannot accidentally call a cached C++ function without a context.
                target = getattr(self._native, name)
                recorder = active_telemetry()
                explicit_id = kwargs.pop("test_id", None)
                if explicit_id is not None and (name in _INTERACTIVE or name.startswith(("input_", "slider_", "drag_", "v_slider_")) or name == "begin_combo"):
                    if args and isinstance(args[0], str):
                        args = (f"{args[0].split('###', 1)[0]}###{explicit_id}", *args[1:])
                    elif isinstance(kwargs.get("label"), str):
                        kwargs["label"] = f"{kwargs['label'].split('###', 1)[0]}###{explicit_id}"
                if recorder is None or not observed:
                    return target(*args, **kwargs)
                source = _source(inspect.currentframe().f_back)
                if name in _END:
                    result = target(*args, **kwargs)
                    if recorder._containers and recorder._containers[-1][0] == name:
                        _, kind, region_id = recorder._containers.pop()
                        recorder.pop_region()
                        if kind in {"group", "table", "tab_bar", "tab"}:
                            region = recorder.region(region_id)
                            recorder.record_region(
                                region_id, str(region["label"]), bool(region["visible"]),
                                _rect(self._native.get_item_rect_min(), self._native.get_item_rect_max()),
                                kind=kind, source=region["source"],
                            )
                    else:
                        recorder.record_error(source["path"], f"Unbalanced container: {name}")
                    return result
                component_width = float(native_imgui.calc_item_width()) if name in _VECTORS else None
                result = target(*args, **kwargs)
                if name == "push_id":
                    recorder._id_stack.append(str(args[0]))
                    return result
                if name == "pop_id":
                    if recorder._id_stack:
                        recorder._id_stack.pop()
                    return result
                if name == "get_window_draw_list":
                    return DrawListFacade(result, recorder, self._native)
                if name == "begin_disabled":
                    recorder._disabled.append(bool(args[0]) if args else bool(kwargs.get("disabled", True)))
                    return result
                if name == "end_disabled":
                    if recorder._disabled:
                        recorder._disabled.pop()
                    return result
                label = _label(name, args, kwargs)
                if name in _CONTAINERS:
                    end, unconditional, kind = _CONTAINERS[name]
                    opened = bool(result[0] if isinstance(result, tuple) else result)
                    if name in {"begin_combo", "begin_menu", "begin_tab_item"}:
                        _record_item(recorder, name, label, source, result, explicit_id, native=self._native)
                    if unconditional or opened:
                        parent = recorder.parent_id or "root"
                        region_id = explicit_id or f"region/{parent}/{_site_id(source, name)}"
                        if "##" in label:
                            region_id += "/" + label.split("##", 1)[1]
                        region_id = recorder.unique_id(region_id)
                        p, size = self._native.get_window_pos(), self._native.get_window_size()
                        recorder.record_region(region_id, label, opened if kind in {"window", "child"} else True,
                                               Rect(p.x, p.y, size.x, size.y), kind=kind, source=source)
                        recorder.push_region(region_id)
                        recorder._containers.append((end, kind, region_id))
                    return result
                options = None
                if name in {"combo", "list_box"}:
                    raw = args[2] if len(args) > 2 else kwargs.get("items")
                    if isinstance(raw, (list, tuple)):
                        options = [str(item) for item in raw]
                    elif isinstance(raw, str):
                        options = [item for item in raw.split("\0") if item]
                _record_item(recorder, name, label, source, result, explicit_id, component_width, native=self._native, options=options)
                return result
            self._wrappers[name] = call
        return self._wrappers[name]


class DrawListFacade:
    """Expose custom drawing geometry without changing native draw commands."""

    def __init__(self, draw_list, recorder, native):
        self._native = native
        self._draw_list = draw_list
        self._recorder = recorder

    def __getattr__(self, name):
        target = getattr(self._draw_list, name)
        if not name.startswith("add_"):
            return target

        def draw(*args, **kwargs):
            result = target(*args, **kwargs)
            points = [arg for arg in args[:4] if isinstance(arg, (tuple, list)) and len(arg) == 2
                      or hasattr(arg, "x") and hasattr(arg, "y")]
            if points:
                source = _source(inspect.currentframe().f_back)
                xy = [(float(p.x), float(p.y)) if hasattr(p, "x") else (float(p[0]), float(p[1])) for p in points]
                if name == "add_text" and len(args) >= 3:
                    size = self._native.calc_text_size(str(args[2]))
                    xy.append((xy[0][0] + size.x, xy[0][1] + size.y))
                xs, ys = zip(*xy)
                base = f"draw/{self._recorder.parent_id}/{_site_id(source, name)}"
                self._recorder.record_widget(
                    self._recorder.unique_id(base), str(args[2]) if name == "add_text" and len(args) > 2 else name,
                    name, True, False, Rect(min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)),
                    source=source, interactive=False,
                )
            return result
        return draw


imgui = ImGuiFacade()
