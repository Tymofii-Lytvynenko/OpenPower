from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from src.shared.system_interfaces import ICheckpointedSystem

SYSTEM_STATE_CHECKPOINT = "checkpoint"
SYSTEM_STATE_CACHE = "cache"
SYSTEM_STATE_HELPER = "helper"
VALID_SYSTEM_STATE_POLICIES = frozenset(
    {
        SYSTEM_STATE_CHECKPOINT,
        SYSTEM_STATE_CACHE,
        SYSTEM_STATE_HELPER,
    }
)


@runtime_checkable
class IRuntimeStateContractSystem(Protocol):
    runtime_state_contract: Mapping[str, str]


def _system_label(system: object) -> str:
    return str(getattr(system, "id", type(system).__name__))


def _instance_state(system: object) -> dict[str, Any]:
    try:
        raw_state = dict(vars(system))
    except TypeError:
        raw_state = {}
        for attr_name in getattr(type(system), "__slots__", ()):
            if hasattr(system, attr_name):
                raw_state[attr_name] = getattr(system, attr_name)

    return {
        name: value
        for name, value in raw_state.items()
        if not callable(value)
    }


def runtime_state_contract(system: object) -> dict[str, str]:
    raw_contract = getattr(system, "runtime_state_contract", {})
    if raw_contract is None:
        return {}
    if not isinstance(raw_contract, Mapping):
        raise TypeError(
            f"System '{_system_label(system)}' runtime_state_contract must be a mapping, "
            f"got {type(raw_contract).__name__}."
        )

    normalized = {str(name): str(policy) for name, policy in raw_contract.items()}
    invalid = {
        name: policy
        for name, policy in normalized.items()
        if policy not in VALID_SYSTEM_STATE_POLICIES
    }
    if invalid:
        raise RuntimeError(
            f"System '{_system_label(system)}' has invalid runtime state policies: {invalid}."
        )
    return normalized


def checkpointed_runtime_fields(system: object) -> tuple[str, ...]:
    contract = runtime_state_contract(system)
    return tuple(
        name
        for name, policy in contract.items()
        if policy == SYSTEM_STATE_CHECKPOINT
    )


def export_declared_checkpoint_state(system: object) -> dict[str, Any]:
    return {
        name: getattr(system, name)
        for name in checkpointed_runtime_fields(system)
    }


def validate_runtime_state_contract(system: object) -> None:
    contract = runtime_state_contract(system)
    instance_state = _instance_state(system)

    undeclared = sorted(name for name in instance_state if name not in contract)
    if undeclared:
        raise RuntimeError(
            f"System '{_system_label(system)}' has undeclared runtime state: {undeclared}. "
            "Declare each attribute in runtime_state_contract so save/load behavior stays explicit."
        )

    checkpoint_fields = set(checkpointed_runtime_fields(system))
    if checkpoint_fields and not isinstance(system, ICheckpointedSystem):
        raise RuntimeError(
            f"System '{_system_label(system)}' declares checkpointed state {sorted(checkpoint_fields)} "
            "but does not implement ICheckpointedSystem."
        )

    if not isinstance(system, ICheckpointedSystem):
        return

    exported = system.export_persistent_state()
    if not isinstance(exported, dict):
        raise TypeError(
            f"System '{_system_label(system)}' export_persistent_state() must return a dict, "
            f"got {type(exported).__name__}."
        )

    exported_keys = set(exported)
    missing = sorted(checkpoint_fields - exported_keys)
    unexpected = sorted(exported_keys - checkpoint_fields)
    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append(f"missing exported keys: {missing}")
        if unexpected:
            details.append(f"unexpected exported keys: {unexpected}")
        raise RuntimeError(
            f"System '{_system_label(system)}' checkpoint contract mismatch: "
            + "; ".join(details)
        )
