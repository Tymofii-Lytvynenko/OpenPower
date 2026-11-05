"""Resolve generic names against a local reference bundle."""

from pathlib import Path


def resolve_reference_file(root: Path, relative_path: str | Path) -> Path:
    """Resolve a generic path against the bundled source files and return one match."""
    relative = Path(relative_path)
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        raise ValueError(f"Expected a relative path inside the reference root: {relative_path}")

    current = Path(root)
    for part in relative.parts:
        direct = current / part
        if direct.exists():
            current = direct
            continue

        normalized = part.casefold()
        suffix = None
        for prefix in ("reference_", "reference-"):
            if normalized.startswith(prefix):
                suffix = normalized[len(prefix):]
                break
        if not suffix or not current.is_dir():
            raise FileNotFoundError(f"Reference path does not exist: {direct}")

        # Generic names stand in for a source prefix; an arbitrary suffix match
        # could silently select an unrelated file with a longer basename.
        matches = [
            candidate
            for candidate in current.iterdir()
            if candidate.name.casefold().endswith(("_" + suffix, "-" + suffix))
        ]
        if len(matches) != 1:
            raise FileNotFoundError(
                f"Expected one reference path match for {part!r} under {current}, "
                f"found {len(matches)}."
            )
        current = matches[0]

    if not current.is_file():
        raise FileNotFoundError(f"Reference path is not a file: {current}")
    return current
