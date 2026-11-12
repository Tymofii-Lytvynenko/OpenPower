from __future__ import annotations

import pytest
import rtoml

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


@pytest.mark.parametrize(
    ("contract_id", "option", "value"),
    [
        (
            "shared-is-leaf",
            "ignore_imports",
            ["src.shared.evasion -> src.engine.simulator"],
        ),
        ("engine-isolation", "allow_indirect_imports", True),
        ("engine-isolation", "as_packages", False),
    ],
    ids=("ignore-imports", "allow-indirect-imports", "as-packages-false"),
)
def test_contract_suppression_options_exit_nonzero(tmp_path, contract_id, option, value):
    custom_fixture_root(tmp_path)
    config_path = tmp_path / "pyproject.toml"
    config = rtoml.loads(config_path.read_text(encoding="utf-8"))
    contract = next(
        item
        for item in config["tool"]["importlinter"]["contracts"]
        if item["id"] == contract_id
    )
    contract[option] = value
    write_file(tmp_path, "pyproject.toml", rtoml.dumps(config))

    if option == "ignore_imports":
        write_file(tmp_path, "src/shared/evasion.py", "import src.engine.simulator\n")

    result = run_architecture_tool(tmp_path)
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert option in output
