import pytest
from hypothesis import given, strategies as st

from src.shared.migrations import MigrationRegistry, SaveMigration


@given(st.integers(1, 5), st.permutations(('z', 'a', 'm')))
def test_migration_chain_runs_by_version_and_owner(length, owners):
    registry = MigrationRegistry()
    for version in range(1, length + 1):
        for owner in owners:
            def migrate(meta, tables, v=version, o=owner):
                meta.setdefault('trace', []).append((v, o))
            registry.register(SaveMigration(version, version + 1, migrate, owner))
    meta = {'version': 1}
    registry.migrate(meta, {}, target_version=length + 1)
    assert meta['version'] == length + 1
    assert meta['trace'] == [(v, o) for v in range(1, length + 1) for o in sorted(owners)]


@given(st.integers(1, 20))
def test_migration_rejects_missing_duplicate_and_future_versions(version):
    migration = SaveMigration(version, version + 1, lambda meta, tables: None, 'owner')
    registry = MigrationRegistry([migration])
    with pytest.raises(RuntimeError, match='Duplicate'):
        registry.register(migration)
    with pytest.raises(RuntimeError, match='No save migration'):
        registry.migrate({'version': version + 1}, {}, target_version=version + 2)
    with pytest.raises(RuntimeError, match='newer'):
        registry.migrate({'version': version + 1}, {}, target_version=version)
