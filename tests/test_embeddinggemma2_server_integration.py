"""Opt-in integration checks for the local EmbeddingGemma 2 server."""

from __future__ import annotations

import json
import math
import os
from urllib.request import Request, urlopen

import pytest


SERVER_URL = os.environ.get("REPOWISE_EMBEDDING_TEST_URL", "").rstrip("/")
MODEL_ID = os.environ.get("REPOWISE_EMBEDDING_TEST_MODEL", "embeddinggemma-2")

pytestmark = pytest.mark.skipif(
    not SERVER_URL,
    reason="set REPOWISE_EMBEDDING_TEST_URL to run local model integration tests",
)


def _get_json(path: str) -> dict:
    with urlopen(f"{SERVER_URL}{path}", timeout=10) as response:
        return json.load(response)


def _embed(texts: list[str]) -> list[dict]:
    body = json.dumps({"model": MODEL_ID, "input": texts}).encode("utf-8")
    request = Request(
        f"{SERVER_URL}/v1/embeddings",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=120) as response:
        return json.load(response)["data"]


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm)


def test_server_health_and_model_alias() -> None:
    assert _get_json("/health")["status"] == "ok"
    model_ids = {entry["id"] for entry in _get_json("/v1/models")["data"]}
    assert MODEL_ID in model_ids


def test_batch_embeddings_are_768d_normalized_and_ordered() -> None:
    result = _embed(
        [
            "A deterministic simulation advances in fixed time steps.",
            "The client renders a snapshot of the current world state.",
            "A treaty changes diplomatic relations between countries.",
        ]
    )

    assert [entry["index"] for entry in result] == [0, 1, 2]
    for entry in result:
        vector = entry["embedding"]
        assert len(vector) == 768
        assert all(math.isfinite(value) for value in vector)
        assert math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0, abs_tol=0.02)


def test_identical_text_produces_stable_vectors() -> None:
    text = "Debt settlement records the paid amount and updates remaining principal."
    first = _embed([text])[0]["embedding"]
    second = _embed([text])[0]["embedding"]

    assert first == second


def test_long_page_fits_the_server_batch_configuration() -> None:
    text = (
        "A state transition updates deterministic simulation data and snapshots. " * 170
    )

    assert len(_embed([text])[0]["embedding"]) == 768


def test_code_search_query_ranks_debt_settlement_first() -> None:
    query = "Which service records debt payments and reduces outstanding principal?"
    documents = [
        "DueDebtSettlementEffects records debt installments, updates the ledger, "
        "reduces outstanding principal, and emits a settlement event.",
        "TreasuryReservePolicy manages reserve targets and foreign currency holdings.",
        "BattleStrategy chooses unit maneuvers from terrain, force strength, and supply.",
        "CentralBarRenderer draws the top navigation bar and its menu icons.",
    ]
    vectors = [entry["embedding"] for entry in _embed([query, *documents])]
    scores = [_cosine(vectors[0], document) for document in vectors[1:]]

    assert scores[0] > max(scores[1:])
