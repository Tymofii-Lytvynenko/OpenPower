from __future__ import annotations

from tests.architecture.helpers import (
    custom_fixture_root,
    run_architecture_tool,
    write_file,
)


def test_cross_module_import_requires_manifest_dependency(tmp_path):
    custom_fixture_root(tmp_path)
    write_file(
        tmp_path,
        "modules/alpha/systems/consumer.py",
        "from modules.base.schema import BASE_SCHEMAS\n",
    )

    result = run_architecture_tool(tmp_path)

    assert result.returncode != 0
    assert "Module 'alpha' imports 'base' without declaring it" in result.stdout
    assert "modules/alpha/systems/consumer.py" in result.stdout


def test_declared_cross_module_dependency_is_allowed(tmp_path):
    custom_fixture_root(tmp_path)
    write_file(
        tmp_path,
        "modules/alpha/mod.toml",
        'id = "alpha"\ndependencies = ["base"]\n',
    )
    write_file(
        tmp_path,
        "modules/alpha/systems/consumer.py",
        "from modules.base.schema import BASE_SCHEMAS\n",
    )

    result = run_architecture_tool(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_manifest_dependency_cycle_exits_nonzero_with_cycle_path(tmp_path):
    custom_fixture_root(tmp_path)
    write_file(
        tmp_path,
        "modules/base/mod.toml",
        'id = "base"\ndependencies = ["alpha"]\n',
    )
    write_file(
        tmp_path,
        "modules/alpha/mod.toml",
        'id = "alpha"\ndependencies = ["base"]\n',
    )

    result = run_architecture_tool(tmp_path)

    assert result.returncode != 0
    assert "Circular mod dependency: alpha -> base -> alpha" in result.stdout


def test_dependencies_use_manifest_ids_not_directory_names(tmp_path):
    custom_fixture_root(tmp_path)
    write_file(tmp_path, 'modules/base/mod.toml', 'id = "foundation"\ndependencies = []\n')
    write_file(tmp_path, 'modules/alpha/mod.toml', 'id = "alpha"\ndependencies = ["foundation"]\n')
    write_file(tmp_path, 'modules/alpha/consumer.py', 'from modules.base import schema\n')
    result = run_architecture_tool(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_relative_import_from_package_initializer_requires_dependency(tmp_path):
    custom_fixture_root(tmp_path)
    write_file(tmp_path, 'modules/alpha/__init__.py', 'from .. import base\n')
    result = run_architecture_tool(tmp_path)
    assert result.returncode != 0
    assert "Module 'alpha' imports 'base' without declaring it" in result.stdout
