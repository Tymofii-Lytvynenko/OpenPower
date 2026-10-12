from __future__ import annotations

import json
import os
from uuid import uuid4
from pathlib import Path


def run_live_smoke(output: Path) -> int:
    """Verify file commands and screenshots against a real hidden Arcade window."""
    import arcade
    from src.client.services.imgui_service import ImGuiService
    from src.client.ui.core.instrumented_imgui import imgui

    output.mkdir(parents=True, exist_ok=True)
    commands_path = output / "commands.json"
    commands_path.write_text('{"commands": []}', encoding="utf-8")
    previous = os.environ.get("OPENPOWER_UI_ARTIFACTS")
    os.environ["OPENPOWER_UI_ARTIFACTS"] = str(output.resolve())
    window = None
    service = None
    prefix = str(uuid4())
    try:
        window = arcade.Window(640, 480, visible=False)
        service = ImGuiService(window)
        service._ui_bridge.interval = 0
        checked, text = False, "before"
        for frame in range(35):
            window.switch_to()
            window.clear()
            service.new_frame()
            imgui.set_next_window_pos((20, 20))
            imgui.set_next_window_size((500, 300))
            imgui.begin("Live bridge verification")
            _, checked = imgui.checkbox("Toggle", checked)
            _, text = imgui.input_text("Name", text)
            imgui.end()
            service.render()
            if frame == 2:
                commands_path.write_text(json.dumps({"commands": [
                    {"id": f"{prefix}.toggle", "op": "click", "target": {"label": "Toggle", "type": "checkbox"}},
                    {"id": f"{prefix}.name", "op": "input", "target": {"label": "Name", "type": "input_text"}, "value": "after"},
                ]}), encoding="utf-8")
            window.flip()
        completed = [r for r in service._ui_bridge.results if r["id"].startswith(prefix)]
        passed = checked and text == "after" and len(completed) == 2 and all(r["passed"] for r in completed)
        print(f"Live UI bridge {'PASS' if passed else 'FAIL'}: checkbox={checked}, text={text!r}")
        print(f"Report: {(output / 'report.json').resolve()}")
        return 0 if passed else 1
    finally:
        if service is not None:
            service.shutdown()
        if window is not None:
            window.close()
        if previous is None:
            os.environ.pop("OPENPOWER_UI_ARTIFACTS", None)
        else:
            os.environ["OPENPOWER_UI_ARTIFACTS"] = previous
