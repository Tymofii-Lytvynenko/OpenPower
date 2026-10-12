from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import RLock
from typing import Iterator


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    def to_dict(self) -> dict[str, float]:
        return {
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "width": round(self.width, 2),
            "height": round(self.height, 2),
        }


@dataclass(slots=True)
class _RegionRecord:
    test_id: str
    label: str
    visible: bool
    rect: Rect
    last_seen_frame: int
    parent_id: str | None = None
    kind: str = "window"
    source: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.test_id,
            "label": self.label,
            "visible": self.visible,
            "rect": self.rect.to_dict(),
            "parent_id": self.parent_id,
            "last_seen_frame": self.last_seen_frame,
            "kind": self.kind,
            "source": self.source,
        }


@dataclass(slots=True)
class _WidgetRecord:
    test_id: str
    imgui_id: int
    label: str
    widget_type: str
    visible: bool
    enabled: bool
    rect: Rect
    last_seen_frame: int
    parent_id: str | None = None
    ever_visible: bool = False
    ever_enabled: bool = False
    source: dict[str, object] = field(default_factory=dict)
    interactive: bool = True
    value: object = None
    components: list[dict] = field(default_factory=list)
    options: list[str] = field(default_factory=list)

    def update(self, *, visible: bool, enabled: bool, rect: Rect, frame: int) -> None:
        self.visible = visible
        self.enabled = enabled
        self.rect = rect
        self.last_seen_frame = frame
        self.ever_visible = self.ever_visible or visible
        self.ever_enabled = self.ever_enabled or enabled

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.test_id,
            "imgui_id": self.imgui_id,
            "label": self.label,
            "type": self.widget_type,
            "visible": self.visible,
            "enabled": self.enabled,
            "ever_visible": self.ever_visible,
            "ever_enabled": self.ever_enabled,
            "rect": self.rect.to_dict(),
            "parent_id": self.parent_id,
            "last_seen_frame": self.last_seen_frame,
            "source": self.source,
            "interactive": self.interactive,
            "value": self.value,
            "components": self.components,
            "options": self.options,
        }


class UIRunTelemetry:
    """Collect semantic widget state and geometry during an opted-in UI run."""

    def __init__(self, viewport_size: tuple[int, int]):
        self.viewport_size = viewport_size
        self.frame_count = 0
        self._regions: dict[str, _RegionRecord] = {}
        self._widgets: dict[str, _WidgetRecord] = {}
        self._automatic_by_native: dict[int, list[str]] = {}
        self._lock = RLock()
        self._occurrences: dict[str, int] = {}
        self._containers: list[tuple[str, str, object]] = []
        self._disabled: list[bool] = []
        self._id_stack: list[str] = []
        self.errors: list[dict[str, str]] = []

    @contextmanager
    def frame(self) -> Iterator[None]:
        with self._lock:
            self.frame_count += 1
            self._occurrences.clear()
            self._automatic_by_native.clear()
            self._containers.clear()
            self._disabled.clear()
            self._id_stack.clear()
        recorder_token = _active_recorder.set(self)
        region_token = _active_regions.set(())
        try:
            yield
        finally:
            _active_regions.reset(region_token)
            _active_recorder.reset(recorder_token)

    def record_region(self, test_id: str, label: str, visible: bool, rect: Rect,
                      *, kind: str = "window", source: dict[str, object] | None = None) -> None:
        regions = _active_regions.get()
        parent_id = regions[-1] if regions else None
        with self._lock:
            self._regions[test_id] = _RegionRecord(
                test_id=test_id,
                label=label,
                visible=visible,
                rect=rect,
                last_seen_frame=self.frame_count,
                parent_id=parent_id,
                kind=kind,
                source=source or {},
            )

    def record_widget(
        self,
        test_id: str,
        label: str,
        widget_type: str,
        visible: bool,
        enabled: bool,
        rect: Rect,
        imgui_id: int = 0,
        *, source: dict[str, object] | None = None, interactive: bool = True,
        value: object = None,
    ) -> None:
        regions = _active_regions.get()
        parent_id = regions[-1] if regions else None
        with self._lock:
            record = self._widgets.get(test_id)
            if test_id.startswith("auto/") and imgui_id:
                self._automatic_by_native.setdefault(imgui_id, []).append(test_id)
            if record is None:
                self._widgets[test_id] = _WidgetRecord(
                    test_id=test_id,
                    imgui_id=imgui_id,
                    label=label,
                    widget_type=widget_type,
                    visible=visible,
                    enabled=enabled,
                    rect=rect,
                    last_seen_frame=self.frame_count,
                    parent_id=parent_id,
                    ever_visible=visible,
                    ever_enabled=enabled,
                    source=source or {},
                    interactive=interactive,
                    value=value,
                )
                return
            if record.last_seen_frame == self.frame_count and not test_id.startswith(("auto/", "draw/", "plot-item/")):
                self.record_error(test_id, "Duplicate semantic widget ID in one frame.")
            record.update(
                visible=visible,
                enabled=enabled,
                rect=rect,
                frame=self.frame_count,
            )
            record.parent_id = parent_id
            record.imgui_id = imgui_id
            record.label = label
            record.source = source or record.source
            record.interactive = interactive
            record.value = value

    def to_dict(self) -> dict[str, object]:
        with self._lock:
            return {
                "viewport": {"width": self.viewport_size[0], "height": self.viewport_size[1]},
                "coordinate_space": "imgui_screen_logical_top_left",
                "frames": self.frame_count,
                "regions": [self._current(record) for record in self._regions.values()],
                "widgets": [self._current(record) for record in self._widgets.values()],
                "errors": list(self.errors),
            }

    def widget(self, test_id: str) -> dict[str, object] | None:
        with self._lock:
            record = self._widgets.get(test_id)
            return self._current(record) if record else None

    def region(self, test_id: str) -> dict[str, object] | None:
        with self._lock:
            record = self._regions.get(test_id)
            return self._current(record) if record else None

    def _current(self, record) -> dict[str, object]:
        result = record.to_dict()
        result["present"] = record.last_seen_frame == self.frame_count
        if not result["present"]:
            result["visible"] = False
        return result

    def unique_id(self, base: str) -> str:
        count = self._occurrences.get(base, 0)
        self._occurrences[base] = count + 1
        return base if count == 0 else f"{base}/{count}"

    def push_region(self, test_id: str) -> None:
        _active_regions.set((*_active_regions.get(), test_id))

    def pop_region(self) -> None:
        _active_regions.set(_active_regions.get()[:-1])

    @property
    def parent_id(self) -> str | None:
        regions = _active_regions.get()
        return regions[-1] if regions else None

    @property
    def enabled(self) -> bool:
        return not any(self._disabled)

    def record_error(self, source: str, message: str) -> None:
        with self._lock:
            error = {"source": source, "message": message}
            if error not in self.errors:
                self.errors.append(error)

    def replace_automatic_item(self, native_id: int) -> dict[str, object]:
        metadata = {}
        with self._lock:
            # Semantic aliases are registered frequently in the HUD. Scanning
            # all historical controls here made recording cost grow with usage.
            for key in self._automatic_by_native.pop(native_id, []):
                record = self._widgets.get(key)
                if record is not None:
                    metadata = record.to_dict()
                    del self._widgets[key]
        return metadata

    def set_components(self, test_id: str, components: list[dict]) -> None:
        with self._lock:
            self._widgets[test_id].components = components

    def set_options(self, test_id: str, options: list[str]) -> None:
        with self._lock:
            self._widgets[test_id].options = options


_active_recorder: ContextVar[UIRunTelemetry | None] = ContextVar(
    "openpower_ui_telemetry_recorder", default=None
)
_active_regions: ContextVar[tuple[str, ...]] = ContextVar(
    "openpower_ui_telemetry_regions", default=()
)


def active_telemetry() -> UIRunTelemetry | None:
    return _active_recorder.get()


@contextmanager
def semantic_region(test_id: str, label: str, *, visible: bool = True) -> Iterator[None]:
    recorder = _active_recorder.get()
    if recorder is None:
        yield
        return

    from imgui_bundle import imgui

    position = imgui.get_window_pos()
    size = imgui.get_window_size()
    recorder.record_region(
        test_id,
        label,
        visible and not imgui.is_window_collapsed(),
        Rect(float(position.x), float(position.y), float(size.x), float(size.y)),
    )
    region_token = _active_regions.set((*_active_regions.get(), test_id))
    try:
        yield
    finally:
        _active_regions.reset(region_token)


def record_last_item(
    test_id: str,
    label: str,
    widget_type: str,
    *,
    enabled: bool = True,
) -> None:
    recorder = _active_recorder.get()
    if recorder is None:
        return

    from imgui_bundle import imgui

    minimum = imgui.get_item_rect_min()
    maximum = imgui.get_item_rect_max()
    native_id = int(imgui.get_item_id())
    # Explicit semantic IDs replace automatic records for the same item.
    metadata = recorder.replace_automatic_item(native_id)
    recorder.record_widget(
        test_id,
        label,
        widget_type,
        bool(imgui.is_item_visible()),
        enabled and bool(metadata.get("enabled", True)),
        Rect(
            float(minimum.x),
            float(minimum.y),
            float(maximum.x - minimum.x),
            float(maximum.y - minimum.y),
        ),
        imgui_id=native_id,
        source=metadata.get("source", {}),
        value=metadata.get("value"),
    )
    recorder.set_components(test_id, metadata.get("components", []))
    recorder.set_options(test_id, metadata.get("options", []))
