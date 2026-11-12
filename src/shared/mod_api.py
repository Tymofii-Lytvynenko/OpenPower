from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias, TypeVar

from src.shared.migrations import SaveMigration
from src.shared.schema import TableSchema
from src.shared.system_interfaces import ISystem, SystemAccess

ENGINE_MOD_API_VERSION = 1
CLIENT_PRESENTATION_API_VERSION = 1
SystemFactory: TypeAlias = Callable[[], ISystem]
SystemSpec: TypeAlias = ISystem | type[ISystem] | SystemFactory
T = TypeVar("T")


class ClientPresentationKeys:
    """Stable contribution keys for optional, client-only mod extensions."""

    READINESS_POLICY_FACTORY = "base.military.readiness_policy_factory"
    COVERT_OPERATIONS_FACTORY = "base.military.covert_operations_factory"
    COVERT_SKILL_LEVELS = "base.military.covert_skill_levels"
    DOMESTIC_SECURITY_COVERAGE = "base.military.domestic_security_coverage"
    WEAPONS_TRADE_POLICY_FACTORY = "base.military.weapons_trade_policy_factory"
    UNIT_UPKEEP_BY_ID = "base.military.unit_upkeep_by_id"
    DEFAULT_ROLE_PROFILES = "base.military.default_role_profiles"
    CAPABILITY_BOUNDS = "base.military.capability_bounds"
    CAPABILITY_METADATA = "base.military.capability_metadata"
    CANONICAL_ROLE = "base.military.canonical_role"
    INITIAL_PRODUCTION_ETA_DAYS = "base.military.initial_production_eta_days"
    FOREIGN_GOVERNMENT_CHANGE_RESTRICTION = "base.politics.foreign_government_change_restriction"
    DIPLOMACY_SYSTEM_FACTORY = "base.politics.diplomacy_system_factory"
    COUNTRY_DIPLOMACY_RESTRICTION = "base.politics.country_diplomacy_restriction"
    TREATY_TITLE_RESTRICTION = "base.politics.treaty_title_restriction"


@dataclass(frozen=True)
class ClientPresentationContribution:
    """Client-side presentation helpers loaded independently from simulation systems."""

    api_version: int
    values: Mapping[str, Any]


@dataclass(frozen=True)
class ModContribution:
    """Normalized runtime contribution consumed by the engine."""

    systems: tuple[ISystem, ...] = ()
    table_schemas: tuple[TableSchema, ...] = ()
    save_migrations: tuple[SaveMigration, ...] = ()


@dataclass(frozen=True)
class ModFeature:
    """Reusable group of systems and data contracts for large mods."""

    system_specs: tuple[SystemSpec, ...] = ()
    table_schemas: tuple[TableSchema, ...] = ()
    save_migrations: tuple[SaveMigration, ...] = ()
    name: str = ""


def feature(
    *systems: SystemSpec,
    schemas: TableSchema | Iterable[TableSchema] = (),
    migrations: SaveMigration | Iterable[SaveMigration] = (),
    name: str = "",
) -> ModFeature:
    """Declare a reusable feature pack without instantiating its systems yet."""

    return ModFeature(
        system_specs=tuple(systems),
        table_schemas=_normalize_values(schemas, TableSchema, "schemas"),
        save_migrations=_normalize_values(migrations, SaveMigration, "migrations"),
        name=str(name),
    )


def mod(
    *systems: SystemSpec,
    features: ModFeature | Iterable[ModFeature] = (),
    schemas: TableSchema | Iterable[TableSchema] = (),
    migrations: SaveMigration | Iterable[SaveMigration] = (),
) -> ModContribution:
    """Build a strict contribution from a concise, modder-facing declaration.

    System classes are instantiated automatically. Preconfigured instances and
    zero-argument factories are also accepted, so simple mods stay terse while
    larger mods can compose reusable feature packs.
    """

    system_entries = [(system, "mod") for system in systems]
    table_schemas = list(_normalize_values(schemas, TableSchema, "schemas"))
    save_migrations = list(
        _normalize_values(migrations, SaveMigration, "migrations")
    )

    for pack in _normalize_values(features, ModFeature, "features"):
        context = f"feature '{pack.name}'" if pack.name else "feature"
        system_entries.extend((system, context) for system in pack.system_specs)
        table_schemas.extend(pack.table_schemas)
        save_migrations.extend(pack.save_migrations)

    return ModContribution(
        systems=tuple(
            _build_system(spec, context) for spec, context in system_entries
        ),
        table_schemas=tuple(table_schemas),
        save_migrations=tuple(save_migrations),
    )


def _build_system(spec: SystemSpec, context: str) -> ISystem:
    if isinstance(spec, type):
        try:
            candidate = spec()
        except TypeError as exc:
            raise TypeError(
                f"Could not instantiate system class {spec.__name__} in {context}. "
                "Use a zero-argument factory for configured systems."
            ) from exc
    elif _looks_like_system(spec):
        candidate = spec
    elif callable(spec):
        candidate = spec()
    else:
        raise TypeError(
            f"Expected a system class, instance, or factory in {context}; "
            f"got {type(spec).__name__}."
        )

    if not _looks_like_system(candidate):
        raise TypeError(
            f"System factory in {context} produced {type(candidate).__name__}, "
            "which does not implement the ISystem contract."
        )
    return candidate


def _looks_like_system(candidate: object) -> bool:
    return bool(
        isinstance(getattr(candidate, "access", None), SystemAccess)
        and isinstance(getattr(candidate, "id", None), str)
        and isinstance(getattr(candidate, "dependencies", None), list)
        and callable(getattr(candidate, "update", None))
    )


def _normalize_values(
    values: T | Iterable[T],
    expected_type: type[T],
    label: str,
) -> tuple[T, ...]:
    if isinstance(values, expected_type):
        return (values,)
    try:
        normalized = tuple(values)
    except TypeError as exc:
        raise TypeError(
            f"{label} must be a {expected_type.__name__} or an iterable of them."
        ) from exc

    invalid = [value for value in normalized if not isinstance(value, expected_type)]
    if invalid:
        raise TypeError(
            f"{label} must contain {expected_type.__name__} values, got "
            f"{type(invalid[0]).__name__}."
        )
    return normalized

