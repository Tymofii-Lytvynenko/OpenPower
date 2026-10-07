from __future__ import annotations

import math
from pathlib import Path

import rtoml

from utils import validate_economy


def _valid_resources() -> dict[str, dict[str, object]]:
    return {
        resource: {
            "production": 1.0,
            "legal": True,
            "is_gov_controlled": False,
            "tax_rate": 0.05,
        }
        for resource in validate_economy.ALL_RESOURCES
    }


def test_validator_accepts_complete_file_with_matching_gdp(tmp_path: Path) -> None:
    file_path = tmp_path / "AAA.toml"
    resources = _valid_resources()
    file_path.write_text(rtoml.dumps({"resources": resources}), encoding="utf-8")

    assert validate_economy.validate_file(file_path, float(len(resources))) == []


def test_validator_reports_missing_extra_and_malformed_resource_rows(tmp_path: Path) -> None:
    file_path = tmp_path / "AAA.toml"
    resources = _valid_resources()
    resources.pop(validate_economy.ALL_RESOURCES[0])
    resources["unlisted_resource"] = {"production": 1.0}
    file_path.write_text(rtoml.dumps({"resources": resources}), encoding="utf-8")

    errors = validate_economy.validate_file(file_path, 1.0)

    assert any("Missing categories" in error for error in errors)
    assert any("Extra categories" in error for error in errors)
    assert any("missing required field" in error for error in errors)


def test_validator_rejects_nonnumeric_and_nonfinite_production_without_crashing(tmp_path: Path) -> None:
    file_path = tmp_path / "AAA.toml"
    resources = _valid_resources()
    resources[validate_economy.ALL_RESOURCES[0]]["production"] = "not-a-number"
    resources[validate_economy.ALL_RESOURCES[1]]["production"] = float("nan")
    file_path.write_text(rtoml.dumps({"resources": resources}), encoding="utf-8")

    errors = validate_economy.validate_file(file_path, 36.0)

    assert any("invalid production" in error.lower() for error in errors)
    assert any("finite" in error.lower() for error in errors)


def test_validator_reports_invalid_gdp_benchmark_without_comparison_error(tmp_path: Path) -> None:
    file_path = tmp_path / "AAA.toml"
    file_path.write_text(rtoml.dumps({"resources": _valid_resources()}), encoding="utf-8")

    errors = validate_economy.validate_file(file_path, "not-a-number")

    assert "Target GDP must be a finite number" in errors
