from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class UnitDesignSelection:
    """Hold view-only design context shared by military panels."""

    design_id: str | None = None

    def select(self, design_id: str | None) -> None:
        value = str(design_id or "").strip()
        self.design_id = value or None

    def clear(self) -> None:
        self.design_id = None


def supports_design_details(design: dict) -> bool:
    """REFERENCE does not open the detail window for Infantry designs."""
    design_id = str(design.get("id") or "").strip()
    class_name = str(design.get("class_name") or "").strip().lower()
    return bool(design_id) and class_name != "infantry"
