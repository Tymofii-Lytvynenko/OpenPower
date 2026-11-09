from types import SimpleNamespace

import pytest

import src.shared.state as state_module
from src.shared.state import GameState, transient_state_fields


def test_get_table_reports_missing_tables() -> None:
    with pytest.raises(KeyError, match="Table 'unknown' not found"):
        GameState().get_table("unknown")


def test_update_table_requires_a_polars_dataframe() -> None:
    with pytest.raises(TypeError, match="must be a Polars DataFrame"):
        GameState().update_table("countries", [{"id": "AAA"}])


def test_persistence_contract_reports_missing_and_invalid_metadata(monkeypatch) -> None:
    fields = (
        SimpleNamespace(name="unmarked", metadata={}),
        SimpleNamespace(
            name="invalid_policy",
            metadata={state_module.PERSISTENCE_METADATA_KEY: "ephemeral"},
        ),
    )
    monkeypatch.setattr(state_module, "_GAME_STATE_PERSISTENCE_VALIDATED", False)
    monkeypatch.setattr(state_module.dataclasses, "fields", lambda _type: fields)

    with pytest.raises(RuntimeError) as error:
        state_module.validate_game_state_persistence_contract()

    message = str(error.value)
    assert "missing metadata for fields: ['unmarked']" in message
    assert "invalid policies: {'invalid_policy': 'ephemeral'}" in message


def test_transient_state_fields_expose_only_ephemeral_state() -> None:
    names = {field.name for field in transient_state_fields()}

    assert {
        "events",
        "current_actions",
        "_schema_registry",
        "_table_revisions",
    }.issubset(names)
