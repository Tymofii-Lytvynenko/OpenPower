from __future__ import annotations

import pytest

from tests.architecture.helpers import (
    custom_fixture_root,
    run_architecture_tool,
    write_file,
)


@pytest.mark.parametrize(
    "source",
    [
        "import importlib\nimportlib.import_module('src.engine.simulator')\n",
        "from importlib import import_module as load\nload('modules.base.registration')\n",
        "import builtins as bi\nbi.__import__('src.server.session')\n",
        "__import__(make_module_name())\n",
    ],
    ids=("importlib-literal", "importlib-alias", "builtin-alias", "computed-name"),
)
def test_unapproved_dynamic_import_exits_nonzero(tmp_path, source):
    custom_fixture_root(tmp_path)
    write_file(tmp_path, "src/client/dynamic.py", source)

    result = run_architecture_tool(tmp_path)

    assert result.returncode != 0
    assert "Unapproved dynamic import" in result.stdout
    assert "src/client/dynamic.py" in result.stdout


def test_two_declared_dynamic_composition_sites_are_allowed(tmp_path):
    custom_fixture_root(tmp_path)
    write_file(
        tmp_path,
        "src/engine/mod_manager.py",
        """import importlib

class ModManager:
    def load_runtime(self, package_name):
        return importlib.import_module(f"modules.{package_name}.registration")
""",
    )
    write_file(
        tmp_path,
        "src/modding/client_extensions.py",
        """import importlib

def load_client_presentation(package_name):
    return importlib.import_module(f"modules.{package_name}.client_presentation")
""",
    )

    result = run_architecture_tool(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "body",
    [
        "state.update_table('countries', table)",
        "state.remove_table('countries')",
        "state.tables['countries'] = table",
        "state.globals['preferences']['scale'] = 1.0",
        "state.globals.setdefault('flags', []).append('unsafe')",
        "snapshot = session.get_state_snapshot()\nsnapshot.globals['seed'] = 4",
    ],
    ids=("update-table", "remove-table", "table-assignment", "nested-globals", "container-alias", "session-snapshot"),
)
def test_client_authoritative_state_mutations_exit_nonzero(tmp_path, body):
    custom_fixture_root(tmp_path)
    state_parameter = "session" if "session." in body else "state"
    write_file(tmp_path, "src/client/panel.py", f"def render({state_parameter}):\n    {body.replace(chr(10), chr(10) + '    ')}\n")

    result = run_architecture_tool(tmp_path)

    assert result.returncode != 0
    assert "Client code must not" in result.stdout


def test_local_ui_dictionary_mutations_remain_allowed(tmp_path):
    custom_fixture_root(tmp_path)
    write_file(
        tmp_path,
        "src/client/panel.py",
        """def render(view_model):
    local_ui = {"globals": {}}
    local_ui["globals"]["zoom"] = 2
    local_ui["globals"].update({"theme": "dark"})
    return view_model
""",
    )

    result = run_architecture_tool(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
