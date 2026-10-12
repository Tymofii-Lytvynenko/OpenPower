"""Tolerant screenshot comparison with masks for dynamic regions."""
from __future__ import annotations

from pathlib import Path


def compare_screenshots(actual: Path, expected: Path, output: Path,
                        tolerance: float = 0.03, masks: list[dict] | None = None) -> dict:
    import cv2
    import numpy as np

    if not 0 <= tolerance <= 1:
        raise ValueError("Visual tolerance must be between 0 and 1.")
    a, b = cv2.imread(str(actual)), cv2.imread(str(expected))
    if a is None or b is None:
        raise ValueError("Both actual and baseline screenshots must be readable images.")
    if a.shape != b.shape:
        return {"passed": False, "reason": "image_size_mismatch", "actual_shape": list(a.shape), "expected_shape": list(b.shape)}
    valid = np.ones(a.shape[:2], dtype=bool)
    for mask in masks or []:
        x, y, w, h = (int(mask[k]) for k in ("x", "y", "width", "height"))
        if w < 0 or h < 0:
            raise ValueError("Mask dimensions cannot be negative.")
        valid[max(0, y):max(0, y+h), max(0, x):max(0, x+w)] = False
    if not valid.any():
        raise ValueError("Visual masks exclude the entire image.")
    delta = cv2.absdiff(cv2.GaussianBlur(a, (3, 3), 0), cv2.GaussianBlur(b, (3, 3), 0))
    changed = (delta.max(axis=2) > 20) & valid
    ratio = float(changed.sum() / valid.sum())
    highlighted = a.copy()
    highlighted[changed] = (0, 0, 255)
    output.mkdir(parents=True, exist_ok=True)
    diff = output / "diff.png"
    if not cv2.imwrite(str(diff), highlighted):
        raise OSError("Could not write visual difference image.")
    return {"passed": ratio <= tolerance, "changed_ratio": ratio, "tolerance": tolerance,
            "baseline": str(expected.resolve()), "diff": str(diff.resolve())}
