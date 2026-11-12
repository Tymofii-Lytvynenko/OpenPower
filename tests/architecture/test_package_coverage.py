from __future__ import annotations

from tests.architecture.helpers import (
    custom_fixture_root,
    run_architecture_tool,
    write_file,
)


def test_uncontracted_top_level_src_package_exits_nonzero(tmp_path):
    custom_fixture_root(tmp_path)
    write_file(tmp_path, "src/administration/__init__.py", "\n")

    result = run_architecture_tool(tmp_path)

    assert result.returncode != 0
    assert "Uncontracted src package(s): administration" in result.stdout


def test_import_linter_root_drop_exits_nonzero(tmp_path):
    custom_fixture_root(tmp_path)
    write_file(
        tmp_path,
        "pyproject.toml",
        '[tool.importlinter]\nroot_packages = ["src"]\n',
    )

    result = run_architecture_tool(tmp_path)

    assert result.returncode != 0
    assert "root_packages must be exactly ['src', 'modules']" in result.stdout


def test_every_gameplay_module_requires_a_manifest(tmp_path):
    custom_fixture_root(tmp_path)
    write_file(tmp_path, "modules/unregistered/__init__.py", "\n")

    result = run_architecture_tool(tmp_path)

    assert result.returncode != 0
    assert "Every gameplay module needs a mod.toml manifest" in result.stdout
