from pathlib import Path

import pytest

from utils.reference_paths import resolve_reference_file


def test_resolves_exact_and_generic_names(tmp_path: Path) -> None:
    source = tmp_path / "legacy_catalog.json"
    source.write_text("{}", encoding="utf-8")
    assert resolve_reference_file(tmp_path, source.name) == source
    assert resolve_reference_file(tmp_path, "reference_catalog.json") == source


def test_rejects_ambiguous_or_unrelated_suffixes(tmp_path: Path) -> None:
    (tmp_path / "legacy_catalog.json").touch()
    (tmp_path / "other_catalog.json").touch()
    with pytest.raises(FileNotFoundError):
        resolve_reference_file(tmp_path, "reference_catalog.json")
    with pytest.raises(FileNotFoundError):
        resolve_reference_file(tmp_path, "catalog.json")


def test_rejects_paths_outside_root(tmp_path: Path) -> None:
    for path in ("../outside.txt", tmp_path / "outside.txt"):
        with pytest.raises(ValueError):
            resolve_reference_file(tmp_path, path)
