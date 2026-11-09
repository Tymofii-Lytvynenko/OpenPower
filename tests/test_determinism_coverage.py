import pytest

from src.shared.determinism import DeterminismState, DeterministicRuntime


def test_choice_rejects_an_empty_sequence() -> None:
    runtime = DeterministicRuntime(DeterminismState(seed=42))

    with pytest.raises(IndexError, match="empty sequence"):
        runtime.choice([])
