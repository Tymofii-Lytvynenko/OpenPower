from pathlib import Path
from unittest.mock import Mock

import polars as pl

from src.server.io.data_export_manager import DataExporter


def _export(regions: pl.DataFrame, output_root: Path) -> Path:
    config = Mock()
    config.get_write_data_dir.return_value = output_root
    state = Mock()
    state.get_table.return_value = regions

    DataExporter(config).save_regions(state)

    return output_root / "regions" / "regions.tsv"


def test_save_regions_writes_preferred_columns_and_excludes_runtime_fields(
    tmp_path: Path,
) -> None:
    regions = pl.DataFrame(
        {
            "id": [42],
            "hex": ["#010203"],
            "name": ["North"],
            "owner": ["AAA"],
            "type": ["land"],
            "_editor_note": ["private"],
            "population": [1000],
        }
    )

    output = _export(regions, tmp_path)

    assert output.read_text(encoding="utf-8").splitlines() == [
        "hex\tname\towner\ttype",
        "#010203\tNorth\tAAA\tland",
    ]


def test_save_regions_keeps_only_available_preferred_columns(tmp_path: Path) -> None:
    regions = pl.DataFrame(
        {
            "description": ["capital"],
            "id": [7],
            "_temporary": ["ignored"],
            "hex": ["#040506"],
        }
    )

    output = _export(regions, tmp_path)

    assert output.read_text(encoding="utf-8").splitlines() == [
        "hex",
        "#040506",
    ]
