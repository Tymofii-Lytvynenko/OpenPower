import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from modules.base.systems.economy.budget_system import BudgetSystem
from modules.base.systems.world.advisor_settings_system import AdvisorSettingsSystem
from modules.base.systems.world.ai_system import AISystem
from modules.base.systems.world.advisor_recommendation_system import AdvisorRecommendationSystem
from modules.base.systems.world.bootstrap_system import BootstrapSystem
from src.shared.actions import (
    ActionBuyMarketUnit,
    ActionRequestDebtContract,
    ActionResolveAdvisorRecommendation,
    ActionResolveDebtContract,
    ActionUpdateAdvisorSettings,
    ActionUpdateBudget,
)
from src.shared.events import EventNewDay
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_HELPER
from src.engine.simulator import Engine


class _AdvisorDaySignal(ISystem):
    access = SystemAccess(phase=SystemPhase.CLOCK)
    runtime_state_contract = {}

    @property
    def id(self) -> str:
        return "base.time"

    @property
    def dependencies(self) -> list[str]:
        return []

    def update(self, state: GameState, delta_time: float) -> None:
        state.events.append(EventNewDay(day=2, month=1, year=2001))


class _AdvisorSystemDependency(ISystem):
    access = SystemAccess(phase=SystemPhase.POPULATION)
    runtime_state_contract = {"_system_id": SYSTEM_STATE_HELPER}

    def __init__(self, system_id: str) -> None:
        self._system_id = system_id

    @property
    def id(self) -> str:
        return self._system_id

    @property
    def dependencies(self) -> list[str]:
        return []

    def update(self, state: GameState, delta_time: float) -> None:
        return


def _state() -> GameState:
    state = GameState(
        tables={
            "countries": pl.DataFrame({"id": ["UKR", "POL"]}),
        }
    )
    ensure_base_tables(state)
    state.globals["player_country_map"] = {"player-a": "UKR"}
    return state


def _action(
    player_id: str = "player-a",
    country_tag: str = "UKR",
    economy_status: str = "automatic",
    politics_status: str = "confirmations",
    military_status: str = "manual",
) -> ActionUpdateAdvisorSettings:
    return ActionUpdateAdvisorSettings(
        player_id,
        country_tag,
        economy_status,
        politics_status,
        military_status,
    )


def test_advisor_modes_are_updated_on_the_authoritative_country_row():
    state = _state()
    state.current_actions = [_action()]

    AdvisorSettingsSystem().update(state, 0.0)

    ukraine = state.tables["countries"].filter(pl.col("id") == "UKR").row(0, named=True)
    assert ukraine["advisor_economy_status"] == "automatic"
    assert ukraine["advisor_politics_status"] == "confirmations"
    assert ukraine["advisor_military_status"] == "manual"
    assert state.journal.command_results[-1]["status"] == "applied"


def test_advisor_settings_reject_unowned_countries_without_mutation():
    state = _state()
    state.current_actions = [_action(country_tag="POL")]

    AdvisorSettingsSystem().update(state, 0.0)

    poland = state.tables["countries"].filter(pl.col("id") == "POL").row(0, named=True)
    assert poland["advisor_economy_status"] == "manual"
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert "does not control" in state.journal.command_results[-1]["reason"]


def test_advisor_settings_reject_unknown_modes_without_mutation():
    state = _state()
    state.current_actions = [_action(economy_status="automatic-ish")]

    AdvisorSettingsSystem().update(state, 0.0)

    ukraine = state.tables["countries"].filter(pl.col("id") == "UKR").row(0, named=True)
    assert ukraine["advisor_economy_status"] == "manual"
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert "valid advisor mode" in state.journal.command_results[-1]["reason"]


def test_advisor_settings_reject_when_country_data_is_unavailable():
    for countries in (None, pl.DataFrame({"name": ["UKR"]})):
        state = _state()
        if countries is None:
            state.tables.pop("countries")
        else:
            state.tables["countries"] = countries
        state.current_actions = [_action()]

        AdvisorSettingsSystem().update(state, 0.0)

        result = state.journal.command_results[-1]
        assert result["status"] == "rejected"
        assert result["reason"] == "Country data is unavailable."


def test_advisor_settings_reject_missing_or_ambiguous_country_rows():
    unavailable = _state()
    unavailable.current_actions = [_action(country_tag="MISSING")]
    AdvisorSettingsSystem().update(unavailable, 0.0)
    assert unavailable.journal.command_results[-1]["reason"] == (
        "The selected country is unavailable."
    )

    ambiguous = _state()
    countries = ambiguous.tables["countries"]
    ambiguous.tables["countries"] = pl.concat([countries, countries.head(1)])
    ambiguous.current_actions = [_action()]
    AdvisorSettingsSystem().update(ambiguous, 0.0)
    assert ambiguous.journal.command_results[-1]["reason"] == (
        "The selected country is ambiguous."
    )


def test_automatic_advisor_runs_only_the_selected_safe_policy_subset():
    state = _state()
    state.globals["player_tag"] = "UKR"
    state.tables["countries"] = state.tables["countries"].with_columns(
        pl.when(pl.col("id") == "UKR").then(pl.lit(0.0)).otherwise(pl.lit(5000.0)).alias("money_reserves"),
        pl.when(pl.col("id") == "UKR").then(pl.lit(100.0)).otherwise(pl.lit(100.0)).alias("total_annual_revenue"),
        pl.when(pl.col("id") == "UKR").then(pl.lit(1000.0)).otherwise(pl.lit(100.0)).alias("total_annual_expense"),
        pl.when(pl.col("id") == "UKR").then(pl.lit("automatic")).otherwise(pl.lit("manual")).alias("advisor_economy_status"),
    )
    state.events.append(EventNewDay(day=2, month=1, year=2001))

    AISystem().update(state, 0.1)

    player_budget_actions = [
        action for action in state.current_actions
        if isinstance(action, ActionUpdateBudget) and action.country_tag == "UKR"
    ]
    assert player_budget_actions


def test_confirmation_advisor_queues_supported_action_without_executing_it():
    state = _state()
    state.globals["player_tag"] = "UKR"
    state.tables["countries"] = state.tables["countries"].with_columns(
        pl.when(pl.col("id") == "UKR").then(pl.lit(0.0)).otherwise(pl.lit(5000.0)).alias("money_reserves"),
        pl.when(pl.col("id") == "UKR").then(pl.lit(100.0)).otherwise(pl.lit(100.0)).alias("total_annual_revenue"),
        pl.when(pl.col("id") == "UKR").then(pl.lit(1000.0)).otherwise(pl.lit(100.0)).alias("total_annual_expense"),
        pl.when(pl.col("id") == "UKR").then(pl.lit("confirmations")).otherwise(pl.lit("manual")).alias("advisor_economy_status"),
    )
    state.events.append(EventNewDay(day=2, month=1, year=2001))

    AISystem().update(state, 0.1)

    player_budget_actions = [
        action for action in state.current_actions
        if isinstance(action, ActionUpdateBudget) and action.country_tag == "UKR"
    ]
    recommendations = state.tables["advisor_recommendations"].filter(
        pl.col("source_signal").str.starts_with("ai_policy:economy:")
    )
    assert not player_budget_actions
    assert recommendations.height > 0
    assert recommendations[0, "status"] == "active"
    assert "ActionUpdateBudget" in recommendations[0, "optional_action_json"]


def test_advisor_recommendation_answer_executes_only_the_stored_supported_action():
    state = _state()
    state.globals["player_country_map"] = {"player-a": "UKR"}
    state.tables["advisor_recommendations"] = pl.DataFrame([{
            "id": "advisor:ai:UKR:budget-1",
            "campaign_id": "",
            "actor_country_id": "UKR",
            "title": "Economy recommendation: Budget",
            "reason": "Generated by the Budget policy.",
            "source_signal": "ai_policy:economy:budget:budget-1",
            "affected_country_id": "UKR",
            "affected_region_id": 0,
            "confidence": 0.0,
            "urgency": 0.0,
            "expires_at_minute": 10_080,
            "optional_action_json": (
                '{"type":"ActionUpdateBudget","fields":'
                '{"player_id":"ai_system","country_tag":"UKR","allocations":{"education":0.5}}}'
            ),
            "status": "active",
            "created_at_minute": 0,
            "stale_reason": "",
        }], schema=state.tables["advisor_recommendations"].schema, strict=False)
    state.current_actions = [ActionResolveAdvisorRecommendation("player-a", "advisor:ai:UKR:budget-1", True)]

    AdvisorRecommendationSystem().update(state, 0.0)

    assert any(
        isinstance(action, ActionUpdateBudget)
        and action.country_tag == "UKR"
        and action.allocations == {"education": 0.5}
        for action in state.current_actions
    )
    recommendation = state.tables["advisor_recommendations"].filter(
        pl.col("id") == "advisor:ai:UKR:budget-1"
    ).row(0, named=True)
    assert recommendation["status"] == "accepted"
    assert state.journal.command_results[-1]["status"] == "applied"


def test_advisor_recommendation_rejects_a_stored_action_for_another_country():
    state = _state()
    state.globals["player_country_map"] = {"player-a": "UKR"}
    state.tables["advisor_recommendations"] = pl.DataFrame([{
        "id": "advisor:ai:UKR:forged-country",
        "campaign_id": "",
        "actor_country_id": "UKR",
        "title": "Budget recommendation",
        "reason": "The proposed action must remain country scoped.",
        "source_signal": "ai_policy:economy:budget:forged-country",
        "affected_country_id": "UKR",
        "affected_region_id": 0,
        "confidence": 0.0,
        "urgency": 0.0,
        "expires_at_minute": 10_080,
        "optional_action_json": (
            '{"type":"ActionUpdateBudget","fields":'
            '{"player_id":"ai_system","country_tag":"POL","allocations":{"education":0.5}}}'
        ),
        "status": "active",
        "created_at_minute": 0,
        "stale_reason": "",
    }], schema=state.tables["advisor_recommendations"].schema, strict=False)
    state.current_actions = [ActionResolveAdvisorRecommendation("player-a", "advisor:ai:UKR:forged-country", True)]

    AdvisorRecommendationSystem().update(state, 0.0)

    assert len(state.current_actions) == 1
    recommendation = state.tables["advisor_recommendations"].row(0, named=True)
    assert recommendation["status"] == "active"
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert "does not belong" in state.journal.command_results[-1]["reason"]


def test_advisor_recommendation_can_be_dismissed_without_an_action_payload():
    state = _state()
    state.tables["advisor_recommendations"] = pl.DataFrame([{
        "id": "advisor:campaign:read-only",
        "campaign_id": "",
        "actor_country_id": "UKR",
        "title": "Campaign data needs attention",
        "reason": "The message contains guidance and has no action to apply.",
        "source_signal": "campaign:data:missing",
        "affected_country_id": "UKR",
        "affected_region_id": 0,
        "confidence": 0.8,
        "urgency": 0.2,
        "expires_at_minute": 10_080,
        "optional_action_json": "",
        "status": "active",
        "created_at_minute": 0,
        "stale_reason": "",
    }], schema=state.tables["advisor_recommendations"].schema, strict=False)
    state.current_actions = [ActionResolveAdvisorRecommendation("player-a", "advisor:campaign:read-only", False)]

    AdvisorRecommendationSystem().update(state, 0.0)

    recommendation = state.tables["advisor_recommendations"].row(0, named=True)
    assert recommendation["status"] == "dismissed"
    assert state.journal.command_results[-1]["status"] == "applied"
    assert len(state.current_actions) == 1


def test_confirmed_advisor_action_reaches_its_simulation_handler_in_the_same_step():
    state = _state()
    state.globals["player_tag"] = "UKR"
    state.globals["player_country_map"] = {"player-a": "UKR"}
    state.tables["countries"] = state.tables["countries"].with_columns(
        pl.when(pl.col("id") == "UKR").then(pl.lit(0.0)).otherwise(pl.lit(5000.0)).alias("money_reserves"),
        pl.lit(100.0).alias("total_annual_revenue"),
        pl.when(pl.col("id") == "UKR").then(pl.lit(1000.0)).otherwise(pl.lit(100.0)).alias("total_annual_expense"),
        pl.when(pl.col("id") == "UKR").then(pl.lit("confirmations")).otherwise(pl.lit("manual")).alias("advisor_economy_status"),
    )
    engine = Engine(dev_mode=True)
    engine.register_systems([
        _AdvisorDaySignal(),
        BootstrapSystem(),
        _AdvisorSystemDependency("base.economy"),
        _AdvisorSystemDependency("base.trade"),
        AdvisorRecommendationSystem(),
        AISystem(),
        BudgetSystem(),
    ])

    queued = engine.step(state, [], 0.1)

    assert queued.success
    recommendations = state.tables["advisor_recommendations"].filter(
        pl.col("source_signal").str.starts_with("ai_policy:economy:")
    )
    assert recommendations.height > 0
    recommendation_id = str(recommendations[0, "id"])
    assert recommendations[0, "status"] == "active"
    assert state.tables["countries"].filter(pl.col("id") == "UKR")[0, "personal_income_tax_rate"] == 0.2

    accepted = engine.step(
        state,
        [ActionResolveAdvisorRecommendation("player-a", recommendation_id, True)],
        0.1,
    )

    assert accepted.success
    country = state.tables["countries"].filter(pl.col("id") == "UKR").row(0, named=True)
    recommendation = state.tables["advisor_recommendations"].filter(
        pl.col("id") == recommendation_id
    ).row(0, named=True)
    assert recommendation["status"] == "accepted"
    assert country["personal_income_tax_rate"] == 0.22


def test_recommendation_system_reports_unavailable_table_and_rejections_without_mutating_rows():
    unavailable_state = _state()
    unavailable_state.tables.pop("advisor_recommendations")
    unavailable_state.current_actions = [
        ActionResolveAdvisorRecommendation("player-a", "missing-table", True)
    ]

    AdvisorRecommendationSystem().update(unavailable_state, 0.0)

    assert unavailable_state.journal.command_results[-1]["status"] == "rejected"
    assert "unavailable" in unavailable_state.journal.command_results[-1]["reason"]

    state = _state()
    base = {
        "id": "inactive",
        "campaign_id": "",
        "actor_country_id": "UKR",
        "title": "Recommendation",
        "reason": "Test recommendation",
        "source_signal": "test",
        "affected_country_id": "UKR",
        "affected_region_id": 0,
        "confidence": 0.5,
        "urgency": 0.2,
        "expires_at_minute": 10_080,
        "optional_action_json": "",
        "status": "dismissed",
        "created_at_minute": 0,
        "stale_reason": "",
    }
    state.tables["advisor_recommendations"] = pl.DataFrame(
        [
            base,
            {**base, "id": "actionless", "status": "active"},
            {**base, "id": "inactive", "status": "inactive"},
        ],
        schema=state.tables["advisor_recommendations"].schema,
        strict=False,
    )
    state.current_actions = [
        ActionResolveAdvisorRecommendation("player-a", "not-present", True),
        ActionResolveAdvisorRecommendation("player-b", "actionless", True),
        ActionResolveAdvisorRecommendation("player-a", "inactive", True),
        ActionResolveAdvisorRecommendation("player-a", "actionless", True),
    ]

    AdvisorRecommendationSystem().update(state, 0.0)

    results = state.journal.command_results[-4:]
    assert [result["status"] for result in results] == ["rejected"] * 4
    assert "unavailable" in results[0]["reason"]
    assert "does not control" in results[1]["reason"]
    assert "no longer active" in results[2]["reason"]
    assert "no supported action" in results[3]["reason"]
    assert state.tables["advisor_recommendations"]["status"].to_list() == [
        "dismissed", "active", "inactive"
    ]


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "",
        "{",
        "[]",
        '{"type":"UnknownAction","fields":{}}',
        '{"type":"ActionUpdateBudget","fields":[]}',
        '{"type":"ActionUpdateBudget","fields":{"player_id":"human","country_tag":"UKR","allocations":{}}}',
        '{"type":"ActionUpdateBudget","fields":{"player_id":"ai_system"}}',
    ],
)
def test_deserialize_recommendation_rejects_unsupported_or_malformed_actions(payload):
    assert AdvisorRecommendationSystem._deserialize_action(payload) is None


def test_recommendation_action_country_matching_handles_debt_and_market_actions():
    request = ActionRequestDebtContract(
        player_id="ai_system",
        debtor_country_id="ukr",
        creditor_country_id="pol",
        principal=1000,
        annual_interest_rate=0.05,
        payment_frequency_months=12,
        principal_installment=100,
        maturity_months=24,
    )
    assert AdvisorRecommendationSystem._action_matches_country(_state(), request, "UKR")
    assert not AdvisorRecommendationSystem._action_matches_country(_state(), request, "POL")

    contract_action = ActionResolveDebtContract(
        player_id="ai_system", contract_id="contract-1", accept=True
    )
    state = _state()
    assert not AdvisorRecommendationSystem._action_matches_country(state, contract_action, "UKR")
    state.tables["debt_contracts"] = pl.DataFrame({"id": ["contract-1"]})
    assert not AdvisorRecommendationSystem._action_matches_country(state, contract_action, "UKR")
    state.tables["debt_contracts"] = pl.DataFrame(
        {"id": ["contract-1", "contract-2"], "creditor_country_id": ["ukr", "pol"]}
    )
    assert AdvisorRecommendationSystem._action_matches_country(state, contract_action, "UKR")
    assert not AdvisorRecommendationSystem._action_matches_country(state, contract_action, "POL")
    assert not AdvisorRecommendationSystem._action_matches_country(
        state,
        ActionResolveDebtContract(player_id="ai_system", contract_id="missing", accept=True),
        "UKR",
    )

    market_action = ActionBuyMarketUnit(
        player_id="ai_system", listing_id="listing-1", buyer_country_tag="ukr", quantity=1
    )
    assert AdvisorRecommendationSystem._action_matches_country(_state(), market_action, "UKR")
