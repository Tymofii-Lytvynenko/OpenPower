"""Build screenshot contact sheets and check intermediate journey geometry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

from src.client.ui.testing.layout_checks import analyze_layout


def build_review(suite_path: Path, output: Path):
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    entries = []
    for result in suite["results"]:
        report_path = Path(result["report"])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        captures = [step for step in report["details"]["steps"] if step.get("screenshot")]
        if not captures:
            captures = [{"screenshot": report["artifacts"]["screenshot"], "region": "final frame"}]
        for capture in captures:
            screenshot = Path(capture["screenshot"])
            snapshot_path = screenshot.with_suffix(".json")
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8")) if snapshot_path.exists() else report["telemetry"]
            region = next((r for r in snapshot["regions"] if r["id"] == capture["region"]), None)
            entries.append({"journey": result["journey"], "screenshot": str(screenshot),
                            "region": capture["region"], "crop": region["rect"] if region else None,
                            "viewport": report["runtime"]["viewport"],
                            "geometry_errors": [f for f in analyze_layout(snapshot) if f["severity"] == "error"]})
    cell_w, cell_h, per_sheet = 650, 650, 6
    for offset in range(0, len(entries), per_sheet):
        sheet = Image.new("RGB", (cell_w * 3, cell_h * 2), "#343434")
        draw = ImageDraw.Draw(sheet)
        sheet_path = output / f"sheet-{offset // per_sheet + 1:02d}.png"
        for index, entry in enumerate(entries[offset:offset + per_sheet]):
            x, y = (index % 3) * cell_w, (index // 3) * cell_h
            with Image.open(entry["screenshot"]) as screenshot:
                screenshot = screenshot.convert("RGB")
                if entry["crop"]:
                    rect, viewport = entry["crop"], entry["viewport"]
                    sx, sy = screenshot.width / viewport["width"], screenshot.height / viewport["height"]
                    screenshot = screenshot.crop((max(0, int(rect["x"] * sx)), max(0, int(rect["y"] * sy)),
                                                  min(screenshot.width, int((rect["x"] + rect["width"]) * sx)),
                                                  min(screenshot.height, int((rect["y"] + rect["height"]) * sy))))
                screenshot.thumbnail((cell_w - 12, cell_h - 48))
                sheet.paste(screenshot, (x + 6, y + 44))
            draw.text((x + 6, y + 4), f"{offset + index + 1}: {Path(entry['journey']).stem}", fill="white")
            draw.text((x + 6, y + 22), entry["region"], fill="#b2d9ff")
            entry["contact_sheet"] = str(sheet_path)
        sheet.save(sheet_path)
    (output / "inventory.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
    print(f"{len(entries)} captures; {sum(bool(e['geometry_errors']) for e in entries)} with geometry errors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build_review(args.suite, args.output)
