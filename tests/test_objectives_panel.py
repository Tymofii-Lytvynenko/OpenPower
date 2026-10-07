from __future__ import annotations

from types import SimpleNamespace

from src.client.ui.panels.service import objectives_panel as panel_module


class _ImGui:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def text_colored(self, _color, message: str) -> None:
        self.messages.append(message)

    def text_disabled(self, message: str) -> None:
        self.messages.append(message)

    def same_line(self) -> None:
        pass

    def push_text_wrap_pos(self, _value) -> None:
        pass

    def pop_text_wrap_pos(self) -> None:
        pass

    def dummy(self, _size) -> None:
        pass


class _Primitives:
    @staticmethod
    def right_align_text(message: str, _color) -> None:
        pass

    @staticmethod
    def meter(_label: str, _value: float, _color) -> None:
        pass


def test_objective_panel_includes_latest_authoritative_evidence(monkeypatch) -> None:
    fake_imgui = _ImGui()
    monkeypatch.setattr(panel_module, "imgui", fake_imgui)
    monkeypatch.setattr(panel_module, "Prims", _Primitives)
    objective = {
        "title": "Increase oil output",
        "objective_type": "resource_quantity",
        "status": "active",
        "progress": 0.8,
        "current_value": 80.0,
        "target_value": 100.0,
        "remaining": 20.0,
        "deadline_at_minute": 240,
        "hold_duration_minutes": 10,
        "held_minutes": 4,
        "reason": "Condition is not yet satisfied.",
        "evidence_json": '[{"source_table":"domestic_production","game_minute":200,"current_value":80.0,"target_value":100.0,"status":"active"}]',
    }

    panel_module.ObjectivesPanel._render_objective(objective, now=200)

    assert "Current 80.00 / target 100.00; remaining 20.00" in fake_imgui.messages
    assert "Held 4 / 10 minute(s)" in fake_imgui.messages
    assert "Latest evidence: domestic_production at minute 200 (80.00 / 100.00)" in fake_imgui.messages


def test_delegation_summary_exposes_authority_priorities_and_return_condition() -> None:
    summary = panel_module.ObjectivesPanel._delegation_summary({
        "scope_type": "sphere",
        "scope_id": "trade_union",
        "authority_json": '["diplomacy"]',
        "priorities_json": '["treaty_membership"]',
        "return_condition": "campaign_end",
    })

    assert "AI authority: diplomacy" in summary
    assert "priorities: treaty_membership" in summary
    assert "return: campaign end" in summary
