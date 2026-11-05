from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable


@dataclass(frozen=True, slots=True)
class UIAnchor:
    x: float
    y: float
    width: float
    height: float


class UIAnchorRegistry:
    """Track current-frame geometry for explicitly requested UI targets."""

    _targets: frozenset[str] = frozenset()
    _anchors: dict[str, UIAnchor] = {}

    @classmethod
    def set_targets(cls, test_ids: Iterable[str]) -> None:
        targets = frozenset(test_id for test_id in test_ids if test_id)
        if targets != cls._targets:
            cls._targets = targets
            cls._anchors.clear()

    @classmethod
    def is_target(cls, test_id: str | None) -> bool:
        return test_id is not None and test_id in cls._targets

    @classmethod
    def record(
        cls,
        test_id: str | None,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        if not cls.is_target(test_id) or width <= 0.0 or height <= 0.0:
            return
        cls._anchors[test_id] = UIAnchor(x, y, width, height)

    @classmethod
    def get(cls, test_id: str | None) -> UIAnchor | None:
        if not cls.is_target(test_id):
            return None
        return cls._anchors.get(test_id)

    @classmethod
    def begin_frame(cls) -> None:
        cls._anchors.clear()
