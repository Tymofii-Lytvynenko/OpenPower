from dataclasses import dataclass

import pytest

from src.server.command_policy import authorize_country_scope, validate_finite_payload
from src.shared.actions import ActionSetPaused, ActionSetTax, GameAction
from src.shared.commands import CommandEnvelope
from src.shared.state import GameState


@dataclass
class _NestedPayloadAction(GameAction):
    payload: object


def _command(action: GameAction) -> CommandEnvelope:
    return CommandEnvelope(
        command_id="command-test",
        actor_id="player",
        sequence=1,
        action=action,
    )


def test_finite_payload_validation_walks_nested_dataclasses_and_containers() -> None:
    valid = _command(
        _NestedPayloadAction(
            "player",
            {"values": [1.0, (2.0, {3.0})]},
        )
    )
    invalid = _command(ActionSetTax("player", "AAA", float("inf")))

    assert validate_finite_payload(valid, GameState()) is None
    assert validate_finite_payload(invalid, GameState()) == (
        "Command payload contains a non-finite number."
    )


def test_country_scope_authorization_handles_optional_and_wildcard_permissions() -> None:
    state = GameState()
    command = _command(ActionSetTax("player", "AAA", 0.2))

    assert authorize_country_scope(command, state) is None

    state.globals["command_permissions"] = {"player": "*"}
    assert authorize_country_scope(command, state) is None


def test_country_scope_authorization_rejects_missing_and_malformed_permissions() -> None:
    command = _command(ActionSetTax("player", "AAA", 0.2))
    state = GameState()
    state.globals["command_permissions"] = {"another-player": ["AAA"]}

    assert authorize_country_scope(command, state) == (
        "Actor 'player' has no country permissions."
    )

    state.globals["command_permissions"] = {"player": "AAA"}
    assert authorize_country_scope(command, state) == (
        "Actor 'player' has no country permissions."
    )


@pytest.mark.parametrize("allowed", [["AAA"], ("AAA",), {"AAA"}])
def test_country_scope_authorization_accepts_supported_permission_collections(
    allowed: list[str] | tuple[str, ...] | set[str],
) -> None:
    state = GameState()
    state.globals["command_permissions"] = {"player": allowed}

    assert authorize_country_scope(
        _command(ActionSetTax("player", "AAA", 0.2)), state
    ) is None


def test_country_scope_authorization_reports_denied_tags_and_ignores_unscoped_actions() -> None:
    state = GameState()
    state.globals["command_permissions"] = {"player": ["BBB"]}
    denied = authorize_country_scope(
        _command(ActionSetTax("player", "AAA", 0.2)), state
    )
    state.globals["command_permissions"] = {"player": []}
    unscoped = authorize_country_scope(
        _command(ActionSetPaused("player", True)), state
    )

    assert denied == "Actor 'player' cannot control countries ['AAA']."
    assert unscoped is None
