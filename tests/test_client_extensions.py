from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import src.modding.client_extensions as extensions
from modules.base.client_presentation import (
    CovertCreationQuoteService,
    TreatyEligibilityQueryService,
    contribute_client_presentation,
)
from modules.base.systems.military.covert_operations_system import (
    CovertOperationsSystem,
)
from modules.base.systems.world.treaty_diplomacy import DiplomacySystem
from src.shared.mod_api import (
    CLIENT_PRESENTATION_API_VERSION,
    ClientPresentationContribution,
    ClientPresentationKeys,
)


def _config(root: Path, modules: list[SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(
        project_root=root,
        modules_dir=root / "modules",
        active_mods=[module.id for module in modules],
    )


def _manifest(root: Path, module_id: str) -> SimpleNamespace:
    path = root / "modules" / module_id
    path.mkdir(parents=True)
    (path / "client_presentation.py").write_text("\n", encoding="utf-8")
    return SimpleNamespace(id=module_id, path=path)


def test_load_client_presentation_merges_versioned_contribution(monkeypatch, tmp_path):
    manifest = _manifest(tmp_path, "base")
    contribution = ClientPresentationContribution(
        api_version=CLIENT_PRESENTATION_API_VERSION,
        values={"base.key": "value"},
    )
    monkeypatch.setattr(extensions, "discover_mods", lambda _directory: {"base": manifest})
    monkeypatch.setattr(extensions, "resolve_mod_load_order", lambda *_args: [manifest])
    monkeypatch.setattr(
        extensions.importlib,
        "import_module",
        lambda module_name: SimpleNamespace(contribute_client_presentation=lambda: contribution),
    )

    values = extensions.load_client_presentation(_config(tmp_path, [manifest]))

    assert values == {"base.key": "value"}
    assert values.__class__.__name__ == "mappingproxy"


def test_duplicate_presentation_keys_identify_both_mod_owners(monkeypatch, tmp_path):
    first = _manifest(tmp_path, "first")
    second = _manifest(tmp_path, "second")
    contribution = ClientPresentationContribution(
        api_version=CLIENT_PRESENTATION_API_VERSION,
        values={"shared.key": "value"},
    )
    monkeypatch.setattr(extensions, "discover_mods", lambda _directory: {"first": first, "second": second})
    monkeypatch.setattr(extensions, "resolve_mod_load_order", lambda *_args: [first, second])
    monkeypatch.setattr(
        extensions.importlib,
        "import_module",
        lambda _module_name: SimpleNamespace(contribute_client_presentation=lambda: contribution),
    )

    with pytest.raises(RuntimeError, match="first.*second.*shared.key"):
        extensions.load_client_presentation(_config(tmp_path, [first, second]))


def test_unsupported_client_presentation_version_is_rejected(monkeypatch, tmp_path):
    manifest = _manifest(tmp_path, "base")
    contribution = ClientPresentationContribution(api_version=999, values={})
    monkeypatch.setattr(extensions, "discover_mods", lambda _directory: {"base": manifest})
    monkeypatch.setattr(extensions, "resolve_mod_load_order", lambda *_args: [manifest])
    monkeypatch.setattr(
        extensions.importlib,
        "import_module",
        lambda _module_name: SimpleNamespace(contribute_client_presentation=lambda: contribution),
    )

    with pytest.raises(RuntimeError, match="targets client presentation API 999"):
        extensions.load_client_presentation(_config(tmp_path, [manifest]))


def test_modules_without_optional_presentation_extension_are_ignored(monkeypatch, tmp_path):
    manifest = SimpleNamespace(id="headless", path=tmp_path / "modules" / "headless")
    manifest.path.mkdir(parents=True)
    monkeypatch.setattr(extensions, "discover_mods", lambda _directory: {"headless": manifest})
    monkeypatch.setattr(extensions, "resolve_mod_load_order", lambda *_args: [manifest])
    monkeypatch.setattr(
        extensions.importlib,
        "import_module",
        lambda _name: pytest.fail("No provider should be loaded."),
    )

    assert extensions.load_client_presentation(_config(tmp_path, [manifest])) == {}


def test_base_extension_exposes_narrow_queries_instead_of_simulation_systems():
    values = contribute_client_presentation().values
    covert_service = values[ClientPresentationKeys.COVERT_CREATION_QUOTE_SERVICE_FACTORY]()
    treaty_service = values[ClientPresentationKeys.TREATY_ELIGIBILITY_QUERY_SERVICE_FACTORY]()

    assert isinstance(covert_service, CovertCreationQuoteService)
    assert isinstance(treaty_service, TreatyEligibilityQueryService)
    assert not isinstance(covert_service, CovertOperationsSystem)
    assert not isinstance(treaty_service, DiplomacySystem)
    assert not hasattr(covert_service, "update")
    assert not hasattr(treaty_service, "update")
