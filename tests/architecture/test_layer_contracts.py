from __future__ import annotations

import pytest

from tests.architecture.helpers import import_fixture, run_import_linter, write_file


@pytest.mark.parametrize(
    ("source", "forbidden", "source_path", "code"),
    [
        ("src.shared", "src.engine", "src/shared", "import src.engine\n"),
        ("src.core", "src.client", "src/core", "import src.client\n"),
        ("src.engine", "src.server", "src/engine", "import src.server\n"),
        ("src.engine", "modules", "src/engine", "from modules import base\n"),
        ("src.client", "src.engine", "src/client", "import src.engine\n"),
        ("src.server", "src.client", "src/server", "import src.client\n"),
    ],
    ids=("shared-engine", "core-client", "engine-server", "engine-module", "client-engine", "server-client"),
)
def test_forbidden_layer_imports_exit_nonzero(tmp_path, source, forbidden, source_path, code):
    import_fixture(
        tmp_path,
        source=source,
        forbidden=forbidden,
        source_path=source_path,
        source_code=code,
    )

    result = run_import_linter(tmp_path)

    assert result.returncode != 0
    assert "BROKEN" in result.stdout


def test_import_hidden_under_type_checking_is_still_forbidden(tmp_path):
    import_fixture(
        tmp_path,
        source="src.shared",
        forbidden="src.engine",
        source_path="src/shared",
        source_code=(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    import src.engine\n"
        ),
    )

    result = run_import_linter(tmp_path)

    assert result.returncode != 0
    assert "src.shared" in result.stdout


def test_protected_engine_api_rejects_mod_importer(tmp_path):
    import_fixture(
        tmp_path,
        source="modules",
        forbidden="src.engine.mod_manager",
        source_path="modules/base",
        source_code="from src.engine.mod_manager import ModManager\n",
        contract_type="protected",
    )

    result = run_import_linter(tmp_path)

    assert result.returncode != 0
    assert "src.engine.mod_manager" in result.stdout


def test_forbidden_contract_reports_transitive_import_path(tmp_path):
    import_fixture(
        tmp_path,
        source="src.shared",
        forbidden="src.engine",
        source_path="src/shared",
        source_code="import src.core\n",
    )
    write_file(tmp_path, "src/core/__init__.py", "import src.engine\n")

    result = run_import_linter(tmp_path)

    assert result.returncode != 0
    assert "src.shared" in result.stdout
    assert "src.core" in result.stdout
    assert "src.engine" in result.stdout


def test_independence_contract_reports_full_host_cycle(tmp_path):
    import_fixture(
        tmp_path,
        source="src.client",
        forbidden="src.server",
        source_path="src/client",
        source_code="import src.server\n",
        target_code="import src.client\n",
        contract_type="independence",
    )

    result = run_import_linter(tmp_path)

    assert result.returncode != 0
    assert "src.client" in result.stdout
    assert "src.server" in result.stdout


def test_allowed_lower_layer_import_remains_valid(tmp_path):
    import_fixture(
        tmp_path,
        source="src.engine",
        forbidden="src.server",
        source_path="src/engine",
        source_code="import src.core\n",
        target_code="",
    )
    write_file(tmp_path, "src/core/__init__.py", "\n")

    result = run_import_linter(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
