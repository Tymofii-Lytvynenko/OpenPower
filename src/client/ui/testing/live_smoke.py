from __future__ import annotations

import json
import os
from uuid import uuid4
from pathlib import Path


def run_live_smoke(output: Path) -> int:
    """Verify file commands and screenshots against a real hidden Arcade window."""
    import arcade
    from src.client.services.imgui_service import ImGuiService
    from src.client.ui.core.containers import WindowManager
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
        window.push_handlers(
            on_mouse_motion=service.on_mouse_motion,
            on_mouse_press=service.on_mouse_press,
            on_mouse_drag=service.on_mouse_drag,
            on_mouse_release=service.on_mouse_release,
        )
        service._ui_bridge.interval = 0
        checked, text = False, "before"
        panel_id = f"live.smoke.{prefix}"
        for frame in range(80):
            window.switch_to()
            window.dispatch_events()
            window.clear()
            service.new_frame()
            WindowManager.begin_frame()
            with WindowManager.window(
                "Live bridge verification", x=20, y=20, w=500, h=300, test_id=panel_id
            ) as opened:
                if opened:
                    _, checked = imgui.checkbox("Toggle", checked)
                    _, text = imgui.input_text("Name", text)
            service.render()
            if frame == 2:
                commands_path.write_text(json.dumps({"commands": [
                    {"id": f"{prefix}.toggle", "op": "click", "target": {"label": "Toggle", "type": "checkbox"}},
                    {"id": f"{prefix}.name", "op": "input", "target": {"label": "Name", "type": "input_text"}, "value": "after"},
                    {"id": f"{prefix}.move", "op": "pointer_drag", "start": {"x": 100, "y": 27}, "end": {"x": 160, "y": 77}, "steps": 10},
                ]}), encoding="utf-8")
            window.flip()
        completed = [r for r in service._ui_bridge.results if r["id"].startswith(prefix)]
        region = service._ui_bridge.telemetry.region(panel_id)
        position = region["rect"] if region else {}
        moved = abs(position.get("x", 0) - 80) <= 3 and abs(position.get("y", 0) - 70) <= 3
        passed = checked and text == "after" and moved and len(completed) == 3 and all(r["passed"] for r in completed)
        print(f"Live UI bridge {'PASS' if passed else 'FAIL'}: checkbox={checked}, text={text!r}, moved={moved}, position={position}")
        print(f"Report: {(output / 'report.json').resolve()}")
        return 0 if passed else 1
    finally:
        if service is not None:
            service.shutdown()
            WindowManager._placements.pop(f"live.smoke.{prefix}", None)
        if window is not None:
            window.close()
        if previous is None:
            os.environ.pop("OPENPOWER_UI_ARTIFACTS", None)
        else:
            os.environ["OPENPOWER_UI_ARTIFACTS"] = previous
