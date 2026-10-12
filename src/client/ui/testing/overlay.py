"""Make screenshot geometry easy to correlate with machine-readable widget records."""
from __future__ import annotations

from pathlib import Path


def save_overlay(screenshot: Path, output: Path, snapshot: dict, *, frame=None) -> dict:
    import cv2
    image = cv2.imread(str(screenshot)) if frame is None else frame.copy()
    if image is None:
        raise ValueError("Screenshot cannot be read for annotation.")
    sx = image.shape[1] / snapshot["viewport"]["width"]
    sy = image.shape[0] / snapshot["viewport"]["height"]
    legend = []
    for widget in snapshot["widgets"]:
        if not widget["visible"] or not widget.get("present", True) or not widget["interactive"]:
            continue
        number = len(legend) + 1
        rect = widget["rect"]
        x, y, w, h = (int(rect[k] * (sx if k in {"x", "width"} else sy)) for k in ("x", "y", "width", "height"))
        color = (0, 220, 0) if widget["enabled"] else (120, 120, 120)
        cv2.rectangle(image, (x, y), (x + w, y + h), color, 1)
        cv2.putText(image, str(number), (x, max(12, y - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        legend.append({"number": number, "id": widget["id"], "label": widget["label"],
                       "source": widget["source"]})
    if not cv2.imwrite(str(output), image):
        raise OSError("Could not save annotated screenshot.")
    return {"path": str(output.resolve()), "legend": legend,
            "framebuffer_scale": {"x": sx, "y": sy}}
