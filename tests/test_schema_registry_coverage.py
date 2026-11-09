import polars as pl
import pytest

from src.shared.schema import ColumnSpec, TableSchema, WorldSchemaRegistry
from src.shared.state import GameState


def test_register_rejects_empty_schema_names() -> None:
    with pytest.raises(ValueError, match="name cannot be empty"):
        WorldSchemaRegistry([TableSchema(name="", columns={})])


def test_register_rejects_nonpositive_versions() -> None:
    with pytest.raises(ValueError, match="version must be positive"):
        WorldSchemaRegistry(
            [TableSchema(name="items", columns={}, version=0)]
        )


def test_register_rejects_undeclared_key_columns() -> None:
    with pytest.raises(ValueError, match="keys are not declared columns"):
        WorldSchemaRegistry(
            [
                TableSchema(
                    name="items",
                    columns={"id": ColumnSpec(pl.Int64)},
                    key_columns=("missing",),
                )
            ]
        )


def test_register_rejects_conflicting_key_contracts() -> None:
    registry = WorldSchemaRegistry(
        [
            TableSchema(
                name="items",
                columns={"id": ColumnSpec(pl.Int64), "name": ColumnSpec(pl.Utf8)},
                key_columns=("id",),
            )
        ]
    )

    with pytest.raises(RuntimeError, match="keys"):
        registry.register(
            TableSchema(
                name="items",
                columns={"id": ColumnSpec(pl.Int64), "name": ColumnSpec(pl.Utf8)},
                key_columns=("name",),
            )
        )


def test_validate_state_reports_missing_table_and_column() -> None:
    registry = WorldSchemaRegistry(
        [TableSchema(name="items", columns={"id": ColumnSpec(pl.Int64)})]
    )

    missing_table = registry.validate_state(GameState())
    missing_column = registry.validate_state(
        GameState(tables={"items": pl.DataFrame(schema={"extra": pl.Utf8})})
    )

    assert [issue.code for issue in missing_table] == ["missing_table"]
    assert [issue.code for issue in missing_column] == ["missing_column"]


def test_validate_state_reports_wrong_column_dtype() -> None:
    registry = WorldSchemaRegistry(
        [TableSchema(name="items", columns={"id": ColumnSpec(pl.Int64)})]
    )

    issues = registry.validate_state(
        GameState(tables={"items": pl.DataFrame({"id": ["not-an-int"]})})
    )

    assert [issue.code for issue in issues] == ["wrong_dtype"]


def test_validate_state_reports_null_primary_keys() -> None:
    registry = WorldSchemaRegistry(
        [
            TableSchema(
                name="items",
                columns={"id": ColumnSpec(pl.Int64)},
                key_columns=("id",),
            )
        ]
    )

    issues = registry.validate_state(
        GameState(
            tables={"items": pl.DataFrame({"id": [None]}, schema={"id": pl.Int64})}
        )
    )

    assert [issue.code for issue in issues] == ["null_key"]
