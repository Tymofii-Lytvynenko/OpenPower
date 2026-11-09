from unittest.mock import Mock

import polars as pl

from modules.base.systems.economy.due_debt_settlement import (
    DeterministicDueDebtSettlementProcessor,
    DueDebtBatch,
    append_rows,
    replace_rows,
)
from src.shared.state import GameState


def _batch(
    *,
    current_minute: int = 20,
    contracts: dict[str, dict] | None = None,
    payment_queue: list[tuple[int, str]] | None = None,
) -> DueDebtBatch:
    return DueDebtBatch(
        current_minute=current_minute,
        contracts=contracts or {},
        country_rows={},
        balance_columns=(),
        payment_queue=payment_queue or [],
        affected_countries=set(),
        country_balances={},
        changed_countries=set(),
        cause_records=[],
    )


def test_settlement_queue_skips_future_and_closed_contracts() -> None:
    calculator = Mock()
    processor = DeterministicDueDebtSettlementProcessor(calculator)
    effects = Mock()
    batch = _batch(
        contracts={
            "future": {"status": "current"},
            "closed": {"status": "closed"},
        },
        payment_queue=[(20, "closed"), (21, "future")],
    )

    processor._settle_queue(GameState(tables={}), batch, effects)

    calculator.calculate.assert_not_called()
    effects.record_due_debt_settlement.assert_not_called()


def test_country_flush_clears_changes_when_country_rows_cannot_be_patched() -> None:
    processor = DeterministicDueDebtSettlementProcessor(Mock())
    state_without_ids = GameState(
        tables={"countries": pl.DataFrame({"name": ["USA"]})}
    )
    changed = {"USA"}

    processor._flush_country_updates(
        state_without_ids,
        {"USA": {"money_reserves": 10.0}},
        changed,
        ("money_reserves",),
    )
    assert changed == set()

    state_without_matching_country = GameState(
        tables={"countries": pl.DataFrame({"id": ["USA"], "money_reserves": [10.0]})}
    )
    changed = {"CAN"}
    processor._flush_country_updates(
        state_without_matching_country,
        {},
        changed,
        ("money_reserves",),
    )
    assert changed == set()


def test_country_flush_uses_a_unique_order_column_when_legacy_column_exists() -> None:
    processor = DeterministicDueDebtSettlementProcessor(Mock())
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["USA"],
                    "money_reserves": [100.0],
                    "__economic_debt_order": [7],
                }
            )
        }
    )
    changed = {"USA"}

    processor._flush_country_updates(
        state,
        {"USA": {"money_reserves": 90.0}},
        changed,
        ("money_reserves",),
    )

    assert state.get_table("countries")["money_reserves"].to_list() == [90.0]
    assert changed == set()


def test_record_helpers_ignore_missing_tables() -> None:
    state = GameState(tables={})

    append_rows(state, "economic_cause_records", [{"id": "cause-1"}])
    replace_rows(state, "debt_contracts", [{"id": "contract-1"}])

    assert state.tables == {}
