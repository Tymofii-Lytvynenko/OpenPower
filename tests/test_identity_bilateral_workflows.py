from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from modules.base.systems.politics.identity_policy_system import IdentityPolicySystem
from modules.base.systems.world.bilateral_trade_system import BilateralTradeSystem
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.trade_panel import TradePanel
from src.client.ui.testing.fixtures import RecordingClient, build_test_world
from src.shared.actions import (
    ActionCounterTradeDeal, ActionCreateTradeDeal, ActionRespondTradeDeal,
    ActionSetCountryIdentityPolicy, ActionWithdrawTradeDeal,
)
from src.shared.events import EventNewDay


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def world():
    fixture = json.loads((ROOT / "tests/ui/fixtures/identity-trade.json").read_text(encoding="utf-8"))
    fixture["tables"]["diplomatic_trade_deals"] = []
    state = build_test_world(ROOT, fixture)
    state.globals["player_tag"] = "UKR"
    return state


def execute(system, state, action):
    state.events.clear()
    state.current_actions = [action]
    system.update(state, 0.0)


def new_day(system, state, minute=1440):
    state.current_actions = []
    state.events = [EventNewDay(2, 1, 2001)]
    state.time.total_minutes = minute
    system.update(state, 0.0)


@pytest.mark.parametrize("kind,identity_id", [("language", "russian"), ("religion", "catholic")])
def test_identity_policy_changes_authoritative_state_and_pressure(world, kind, identity_id):
    execute(IdentityPolicySystem(), world, ActionSetCountryIdentityPolicy("UKR", "UKR", kind, identity_id, "restricted"))
    row = world.tables["country_identity_groups"].filter(
        (pl.col("identity_type") == kind) & (pl.col("identity_id") == identity_id)
    ).row(0, named=True)
    assert row["legal_status"] == "restricted"
    assert world.tables["country_identity_signals"].item(0, "policy_pressure") > 0
    assert world.journal.command_results[-1]["status"] == "applied"


@pytest.mark.parametrize("actor,identity_id", [("POL", "russian"), ("UKR", "other")])
def test_identity_rejects_foreign_authority_and_aggregate_bucket(world, actor, identity_id):
    before = world.tables["country_identity_groups"].clone()
    execute(IdentityPolicySystem(), world, ActionSetCountryIdentityPolicy(actor, "UKR", "language", identity_id, "illegal"))
    assert world.tables["country_identity_groups"].equals(before)
    assert world.journal.command_results[-1]["status"] == "rejected"


def test_identity_daily_changes_preserve_shares_and_respect_pause(world):
    system = IdentityPolicySystem()
    execute(system, world, ActionSetCountryIdentityPolicy("UKR", "UKR", "language", "russian", "illegal"))
    before = world.tables["country_identity_groups"].clone()
    world.time.is_paused = True
    new_day(system, world, 365 * 1440)
    assert world.tables["country_identity_groups"].equals(before)
    world.time.is_paused = False
    new_day(system, world, 365 * 1440)
    languages = world.tables["country_identity_groups"].filter(pl.col("identity_type") == "language")
    assert languages.filter(pl.col("identity_id") == "russian").item(0, "population_share") < 25
    assert languages["population_share"].sum() == pytest.approx(100)


def proposal(system, state, offered=None, requested=None, days=30):
    execute(system, state, ActionCreateTradeDeal("UKR", "UKR", "POL", offered or [{"type": "cash", "amount": 1000}], requested or [], days))
    return state.tables["diplomatic_trade_deals"].row(-1, named=True)["id"]


def test_trade_settles_cash_territory_and_research_on_both_sides(world):
    system = BilateralTradeSystem()
    offered = [{"type": "cash", "amount": 1000}, {"type": "territory", "region_id": 3}, {"type": "technology", "branch": "land", "level": 3}]
    requested = [{"type": "cash", "amount": 500}, {"type": "territory", "region_id": 4}, {"type": "technology", "branch": "naval", "level": 3}]
    deal_id = proposal(system, world, offered, requested)
    execute(system, world, ActionRespondTradeDeal("POL", deal_id, "POL", True))
    assert world.tables["diplomatic_trade_deals"].item(0, "status") == "accepted"
    balances = {row["id"]: row["money_reserves"] for row in world.tables["countries"].to_dicts()}
    assert balances == {"UKR": 49500, "POL": 50500}
    owners = {row["id"]: row["owner"] for row in world.tables["regions"].to_dicts()}
    assert owners == {1: "UKR", 3: "POL", 2: "POL", 4: "UKR"}
    tracks = {(row["country_id"], row["branch"]): row for row in world.tables["research_tracks"].to_dicts()}
    assert all(row["research_level"] == 3 for row in tracks.values())
    assert "tank" in json.loads(tracks[("POL", "land")]["unlocks_json"])
    assert "frigate" in json.loads(tracks[("UKR", "naval")]["unlocks_json"])


def test_trade_rechecks_assets_without_partial_transfers(world):
    system = BilateralTradeSystem()
    deal_id = proposal(system, world, [{"type": "cash", "amount": 1000}, {"type": "territory", "region_id": 3}])
    world.update_table("countries", world.tables["countries"].with_columns(
        pl.when(pl.col("id") == "UKR").then(0.0).otherwise(pl.col("money_reserves")).alias("money_reserves")))
    countries, regions = world.tables["countries"].clone(), world.tables["regions"].clone()
    execute(system, world, ActionRespondTradeDeal("POL", deal_id, "POL", True))
    assert world.tables["diplomatic_trade_deals"].item(0, "status") == "rejected"
    assert world.tables["countries"].equals(countries)
    assert world.tables["regions"].equals(regions)


def test_trade_counteroffer_links_original_and_can_be_withdrawn(world):
    system = BilateralTradeSystem()
    deal_id = proposal(system, world)
    execute(system, world, ActionCounterTradeDeal("POL", deal_id, "POL", [], [{"type": "cash", "amount": 500}]))
    original, counter = world.tables["diplomatic_trade_deals"].to_dicts()
    assert original["status"] == "countered"
    assert original["countered_by_deal_id"] == counter["id"]
    assert counter["counter_to_deal_id"] == deal_id
    execute(system, world, ActionWithdrawTradeDeal("POL", counter["id"], "POL"))
    assert world.tables["diplomatic_trade_deals"].item(1, "status") == "withdrawn"


def test_trade_expires_before_ai_settlement(world):
    system = BilateralTradeSystem()
    proposal(system, world, days=1)
    new_day(system, world)
    assert world.tables["diplomatic_trade_deals"].item(0, "status") == "expired"
    assert world.tables["countries"]["money_reserves"].sum() == 100000


@pytest.mark.parametrize("requested,status", [(500, "accepted"), (5000, "countered")])
def test_ai_accepts_fair_cash_offer_or_sends_counteroffer(world, requested, status):
    system = BilateralTradeSystem()
    proposal(system, world, requested=[{"type": "cash", "amount": requested}])
    new_day(system, world)
    assert world.tables["diplomatic_trade_deals"].item(0, "status") == status
    if status == "countered":
        assert world.tables["diplomatic_trade_deals"].item(1, "target_country_id") == "UKR"


def test_ui_counteroffer_preserves_terms_from_recipients_perspective(world):
    panel = TradePanel()
    row = {"id": "incoming", "source_country_id": "POL", "offered_assets_json": '[{"type":"cash","amount":500}]',
           "requested_assets_json": '[{"type":"cash","amount":1000}]'}
    panel._begin_counteroffer(row)
    client = RecordingClient(world)
    panel._send_proposal(PanelRenderContext("UKR", True, net_client=client), "UKR", "POL")
    action = client.actions[0]
    assert isinstance(action, ActionCounterTradeDeal)
    assert action.offered_assets == [{"type": "cash", "amount": 1000}]
    assert action.requested_assets == [{"type": "cash", "amount": 500}]
    assert panel.offered_assets == []
    assert action.offered_assets != panel.offered_assets
    assert panel.active_page == "offers"
