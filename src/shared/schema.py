from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from src.shared.state import GameState


@dataclass(frozen=True)
class ColumnSpec:
    dtype: Any
    default: Any = None


@dataclass(frozen=True)
class TableSchema:
    name: str
    columns: Mapping[str, ColumnSpec]
    key_columns: tuple[str, ...] = ()
    version: int = 1
    owner: str = "core"
    preserve_extra_columns: bool = True


@dataclass(frozen=True)
class SchemaIssue:
    table: str
    code: str
    message: str


class WorldSchemaRegistry:
    """Aggregates module-owned table contracts and normalizes state boundaries."""

    def __init__(self, schemas: Iterable[TableSchema] = ()):
        self._schemas: dict[str, TableSchema] = {}
        for schema in schemas:
            self.register(schema)

    @property
    def table_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._schemas))

    def get(self, table_name: str) -> TableSchema | None:
        return self._schemas.get(table_name)

    def register(self, schema: TableSchema) -> None:
        if not schema.name:
            raise ValueError("Table schema name cannot be empty.")
        if schema.version < 1:
            raise ValueError(f"Table '{schema.name}' schema version must be positive.")
        if not set(schema.key_columns).issubset(schema.columns):
            raise ValueError(
                f"Table '{schema.name}' keys are not declared columns: {schema.key_columns}."
            )

        existing = self._schemas.get(schema.name)
        if existing is None:
            self._schemas[schema.name] = schema
            return

        merged_columns = dict(existing.columns)
        for column_name, contribution in schema.columns.items():
            current = merged_columns.get(column_name)
            if current is not None and current.dtype != contribution.dtype:
                raise RuntimeError(
                    f"Schema conflict for '{schema.name}.{column_name}': "
                    f"{current.dtype} vs {contribution.dtype}."
                )
            merged_columns[column_name] = contribution

        if existing.key_columns and schema.key_columns and existing.key_columns != schema.key_columns:
            raise RuntimeError(
                f"Schema conflict for '{schema.name}' keys: "
                f"{existing.key_columns} vs {schema.key_columns}."
            )

        owners = "+".join(dict.fromkeys((existing.owner, schema.owner)))
        self._schemas[schema.name] = TableSchema(
            name=schema.name,
            columns=merged_columns,
            key_columns=existing.key_columns or schema.key_columns,
            version=max(existing.version, schema.version),
            owner=owners,
            preserve_extra_columns=(
                existing.preserve_extra_columns or schema.preserve_extra_columns
            ),
        )

    def register_inferred(self, table_name: str, frame: pl.DataFrame, owner: str = "data") -> None:
        if table_name in self._schemas:
            return
        self.register(
            TableSchema(
                name=table_name,
                columns={
                    column_name: ColumnSpec(dtype=dtype)
                    for column_name, dtype in frame.schema.items()
                },
                owner=owner,
                preserve_extra_columns=True,
            )
        )

    def capture_state(self, state: "GameState", owner: str = "data") -> None:
        for table_name, frame in state.tables.items():
            self.register_inferred(table_name, frame, owner=owner)

    def normalize(self, table_name: str, frame: pl.DataFrame) -> pl.DataFrame:
        schema = self._schemas.get(table_name)
        if schema is None:
            return frame

        normalized = frame
        for column_name, column in schema.columns.items():
            if column_name not in normalized.columns:
                normalized = normalized.with_columns(
                    pl.lit(column.default, dtype=column.dtype).alias(column_name)
                )

        registered = list(schema.columns)
        extras = [column for column in normalized.columns if column not in schema.columns]
        selection = registered + extras if schema.preserve_extra_columns else registered
        return normalized.select(
            [
                pl.col(column_name).cast(schema.columns[column_name].dtype).alias(column_name)
                if column_name in schema.columns
                else pl.col(column_name)
                for column_name in selection
            ]
        )

    def ensure_state(self, state: "GameState") -> None:
        state.bind_schema_registry(self)
        for table_name, schema in self._schemas.items():
            current = state.tables.get(table_name)
            if current is None:
                current = pl.DataFrame(
                    schema={name: column.dtype for name, column in schema.columns.items()}
                )
            state.update_table(table_name, current)

    def validate_state(self, state: "GameState") -> list[SchemaIssue]:
        issues: list[SchemaIssue] = []
        for table_name, schema in self._schemas.items():
            frame = state.tables.get(table_name)
            if frame is None:
                issues.append(SchemaIssue(table_name, "missing_table", "Required table is absent."))
                continue
            for column_name, column in schema.columns.items():
                actual = frame.schema.get(column_name)
                if actual is None:
                    issues.append(
                        SchemaIssue(table_name, "missing_column", f"Missing column '{column_name}'.")
                    )
                elif actual != column.dtype:
                    issues.append(
                        SchemaIssue(
                            table_name,
                            "wrong_dtype",
                            f"Column '{column_name}' is {actual}, expected {column.dtype}.",
                        )
                    )

            if not schema.key_columns or not set(schema.key_columns).issubset(frame.columns):
                continue
            key_expressions = [pl.col(column).is_null() for column in schema.key_columns]
            if frame.filter(pl.any_horizontal(key_expressions)).height:
                issues.append(
                    SchemaIssue(
                        table_name,
                        "null_key",
                        f"Key columns {schema.key_columns} contain null values.",
                    )
                )
            duplicate_groups = (
                frame.group_by(list(schema.key_columns))
                .len()
                .filter(pl.col("len") > 1)
                .height
            )
            if duplicate_groups:
                issues.append(
                    SchemaIssue(
                        table_name,
                        "duplicate_key",
                        f"Table contains {duplicate_groups} duplicate key groups.",
                    )
                )
        return issues

    def versions(self) -> dict[str, int]:
        return {name: schema.version for name, schema in sorted(self._schemas.items())}
