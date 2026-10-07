from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class GameAction:
    """
    Base class for all discrete game actions following the Command Pattern.
    
    Architecture Note:
        In this Data-Oriented architecture, Clients do not modify the GameState directly.
        Instead, they issue Actions. The Engine then processes these Actions deterministically.
        This approach simplifies networking (sending actions) and replays.
    """
    # Identifies who initiated the action ('local_player', 'server', or a specific player ID).
    player_id: str

# --- Map Actions ---

@dataclass
class ActionSetRegionOwner(GameAction):
    """
    Transfers ownership of a specific region to a new country.
    Used by the Editor (painting) and Gameplay (conquest/diplomacy).
    """
    region_id: int
    new_owner_tag: str

# --- Economy Actions ---

@dataclass
class ActionSetTax(GameAction):
    """
    Updates the tax rate for a specific country.
    """
    country_tag: str
    new_tax_rate: float

# --- Time & Control Actions ---

@dataclass
class ActionSetGameSpeed(GameAction):
    """
    Sets the target simulation speed.
    
    Speed Levels (Game Design):
    1: Very Slow (48s / day)
    2: Slow      (24s / day)
    3: Normal    (12s / day)
    4: Fast      (2.4s / day)
    5: Very Fast (0.6s / day)
    """
    speed_level: int

@dataclass
class ActionSetPaused(GameAction):
    """
    Pauses or resumes the simulation.
    Note: The Engine loop continues to run (for UI/Network), but the TimeSystem 
    will stop advancing the game date.
    """
    is_paused: bool
    
@dataclass
class ActionSaveGame(GameAction):
    """
    Triggers the server to serialize the current state to disk.
    """
    save_name: str

@dataclass
class ActionBuildUnit(GameAction):
    """
    Orders a country to recruit a military unit.
    Costs Money and Manpower.
    """
    country_tag: str
    unit_type: str # "infantry", "tank", etc.
    count: int

@dataclass
class ActionMoveUnit(GameAction):
    """
    Orders a unit to move over a validated route to a target region or coordinate.
    """
    unit_id: str
    target_region_id: int
    target_latitude: Optional[float] = None
    target_longitude: Optional[float] = None
    via_region_ids: list[int] = field(default_factory=list)
    is_naval_invasion: bool = False

@dataclass
class ActionAttackUnit(GameAction):
    """
    Orders one unit to initiate an assault against a hostile unit.
    """
    attacker_unit_id: str
    defender_unit_id: str


@dataclass
class ActionSetUnitReadiness(GameAction):
    """Requests a timed readiness posture change for one owned unit."""

    unit_id: str
    target_status: str


@dataclass
class ActionTrainUnit(GameAction):
    """Trains one owned unit to a selected experience level."""

    country_tag: str
    unit_id: str
    target_level: str


@dataclass
class ActionCancelUnitTraining(GameAction):
    """Stops training and returns the unit to its recorded deployment location."""

    unit_id: str


@dataclass
class ActionSetUnitTrainingPaused(GameAction):
    """Pauses or resumes training while preserving completed progress."""

    unit_id: str
    is_paused: bool

@dataclass
class ActionAnnexRegion(GameAction):
    """
    Formal annexation of territory (Change Owner).
    """
    region_id: int
    new_owner_tag: str

@dataclass
class ActionOccupyRegion(GameAction):
    """
    Military occupation (Change Controller, not Owner).
    """
    region_id: int
    new_controller_tag: str

@dataclass
class ActionUpdateBudget(GameAction):
    """
    Updates budget allocation ratios for a country.
    """
    country_tag: str
    allocations: dict # Map of column_name -> ratio (0.0 to 1.0)


@dataclass
class ActionChangeEconomicPolicy(GameAction):
    """Requests a server-validated, effective-dated wage or interest policy change."""

    country_tag: str
    policy_name: str
    target_value: float


@dataclass
class ActionRequestDebtContract(GameAction):
    """Requests foreign financing; the request has no treasury effect before approval."""

    debtor_country_id: str
    creditor_country_id: str
    principal: float
    annual_interest_rate: float
    payment_frequency_months: int
    principal_installment: float
    maturity_months: int
    currency_code: str = "USD"
    conditions: str = ""


@dataclass
class ActionResolveDebtContract(GameAction):
    """Accepts or rejects a pending contract on behalf of its named creditor."""

    contract_id: str
    accept: bool


@dataclass
class ActionRequestDebtRestructuring(GameAction):
    """Requests revised terms for an eligible active debt contract."""

    country_tag: str
    contract_id: str
    annual_interest_rate: float
    payment_frequency_months: int
    principal_installment: float
    maturity_months: int


@dataclass
class ActionUpdateResourcePolicy(GameAction):
    """
    Updates per-resource economic policy for a country's domestic production.
    """
    country_tag: str
    resource_id: str
    is_gov_controlled: bool
    is_legal: bool
    tax_rate: float # Ratio, e.g. 0.05 for 5%


@dataclass
class ActionUpdateGovernment(GameAction):
    """
    Updates the current government profile displayed by the client.
    """
    country_tag: str
    government_type: str
    capital_region_id: Optional[int] = None


@dataclass
class ActionStartCampaign(GameAction):
    """Starts a scenario for one selected country through the authoritative server."""

    scenario_id: str
    country_tag: str


@dataclass
class ActionSetSphereDelegation(GameAction):
    """Changes a bounded campaign delegation without transferring country ownership."""

    country_tag: str
    scope_type: str
    scope_id: str
    delegate_id: str
    authority: list[str] = field(default_factory=list)
    priorities: list[str] = field(default_factory=list)
    active: bool = True
    return_condition: str = "manual"
    next_election: Optional[str] = None
    martial_law: Optional[bool] = None
    election_risk: Optional[float] = None
    ideology_balance: Optional[float] = None


@dataclass
class ActionUpdateInternalLaw(GameAction):
    """
    Updates a single internal law entry for a country.
    """
    country_tag: str
    law_id: str
    status: str
    value: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class ActionUpdateMigrationPolicy(GameAction):
    """
    Updates the migration and border posture for a country.
    """
    country_tag: str
    migration_policy: str
    border_policy: str
    entry_rate: Optional[float] = None
    exit_rate: Optional[float] = None
    asylum_rate: Optional[float] = None
    family_reunification_rate: Optional[float] = None
    skilled_worker_preference: Optional[float] = None
    enforcement_strength: Optional[float] = None
    effective_at_minute: Optional[int] = None


@dataclass
class ActionInvestRegionalInfrastructure(GameAction):
    """Requests a server-quoted upgrade for an owned region and category."""

    country_tag: str
    region_id: int
    category: str
    target_level: float


@dataclass
class ActionCancelInfrastructureProject(GameAction):
    """Cancels an active infrastructure project owned by the acting player."""

    project_id: str


@dataclass
class ActionSetRandomEventControls(GameAction):
    """Updates global or per-category event controls at a simulation boundary."""

    enabled: Optional[bool] = None
    category: str = ""
    category_enabled: Optional[bool] = None
    frequency_multiplier: Optional[float] = None
    maximum_active_events: Optional[int] = None
    seed: Optional[int] = None


@dataclass
class ActionRespondToRandomEvent(GameAction):
    """Requests one authorized, paid response to an active event."""

    event_id: str
    response_id: str
    country_tag: str


@dataclass
class ActionCreateTreaty(GameAction):
    """
    Creates a pending treaty proposal.
    """
    source_country_tag: str
    target_country_tag: str
    treaty_type: str
    title: str
    terms: str

    side_a_country_tags: list[str] = field(default_factory=list)
    side_b_country_tags: list[str] = field(default_factory=list)
    member_country_tags: list[str] = field(default_factory=list)
    conditions: dict[str, Any] = field(default_factory=dict)
    open_to_new_members: bool = False

@dataclass
class ActionRespondTreaty(GameAction):
    """
    Accepts or rejects a pending treaty proposal.
    """
    treaty_id: str
    responder_country_tag: str
    accept: bool


@dataclass
class ActionLeaveTreaty(GameAction):
    """
    Removes a country from an existing treaty.
    """
    treaty_id: str
    country_tag: str


@dataclass
class ActionJoinTreaty(GameAction):
    """Requests admission to an active treaty that accepts eligible members."""

    treaty_id: str
    country_tag: str


@dataclass
class ActionExpelTreatyMember(GameAction):
    """Removes a member when the treaty sponsor needs to enforce its terms."""

    treaty_id: str
    country_tag: str


@dataclass
class ActionQueueUnitProduction(GameAction):
    """
    Adds a new production order for a country's armed forces.
    """
    country_tag: str
    design_id: str
    quantity: int
    priority: int = 1
    training_level: str = "Recruit"


@dataclass
class ActionCancelProductionOrder(GameAction):
    """
    Cancels a queued production order without refunding incurred costs.
    """
    order_id: str


@dataclass
class ActionSetProductionPaused(GameAction):
    """Pauses or resumes a production order without losing completed work."""

    order_id: str
    is_paused: bool


@dataclass
class ActionSetProductionPriority(GameAction):
    """Changes queue priority without resetting completed work."""

    order_id: str
    priority: int


@dataclass
class ActionDispatchUnitDeployment(GameAction):
    """Dispatches all or part of a completed unit group to a legal region."""

    unit_id: str
    destination_region_id: int
    quantity: int = 0


@dataclass
class ActionUpdateResearchFunding(GameAction):
    """
    Updates funding for a named research branch.
    """
    country_tag: str
    branch: str
    funding_ratio: float
    priority: int = 1


@dataclass
class ActionCreateUnitDesign(GameAction):
    """
    Stores a reusable unit design profile.
    """
    country_tag: str
    branch: str
    class_name: str
    display_name: str
    stats: dict[str, Any]


@dataclass
class ActionBuyMarketUnit(GameAction):
    """
    Purchases a unit listing from the market.
    """
    listing_id: str
    buyer_country_tag: str
    quantity: int


@dataclass
class ActionCreateCovertCell(GameAction):
    """
    Establishes a new covert cell.
    """
    country_tag: str
    target_country_tag: str
    cell_name: str


@dataclass
class ActionTrainCovertCell(GameAction):
    """
    Allocates additional training to an existing covert cell.
    """
    cell_id: str
    training_points: float


@dataclass
class ActionStartCovertMission(GameAction):
    """
    Starts a covert mission against a target.
    """
    cell_id: str
    mission_type: str
    target_country_tag: str
    cover_country_tag: Optional[str] = None


@dataclass
class ActionRetireCovertCell(GameAction):
    cell_id: str


@dataclass
class ActionSetCovertCellAssignment(GameAction):
    cell_id: str
    assignment: str


@dataclass
class ActionDeclareWar(GameAction):
    """
    Opens a new war entry between two sides.
    """
    source_country_tag: str
    target_country_tag: str
    casus_belli: str = ""


@dataclass
class ActionOfferPeace(GameAction):
    """
    Proposes a ceasefire or peace settlement.
    """
    war_id: str
    source_country_tag: str
    terms: str = ""


@dataclass
class ActionSubmitPeaceDeal(GameAction):
    """Submits a multi-clause settlement for every member of the opposing war side."""

    war_id: str
    proposer_country_id: str
    offered_clauses: list[dict[str, Any]] = field(default_factory=list)
    requested_clauses: list[dict[str, Any]] = field(default_factory=list)
    expires_after_days: int = 30


@dataclass
class ActionRespondPeaceDeal(GameAction):
    """Records one authorized war participant's response to a peace package."""

    deal_id: str
    responder_country_id: str
    accept: bool


@dataclass
class ActionCastRecognitionVote(GameAction):
    """Casts or replaces one country's vote in an open recognition case."""

    case_id: str
    country_tag: str
    vote: str


@dataclass
class ActionChangePoliticalLaw(GameAction):
    """Requests an authorized, effective-dated domestic law transition."""

    country_tag: str
    law_id: str
    target_value: str
    decision_reason: str = ""


@dataclass
class ActionSetElectionOverride(GameAction):
    """Requests a government-configured election schedule override."""

    country_tag: str
    override_type: str
    duration_days: int
    decision_reason: str = ""


@dataclass
class ActionResolvePoliticalCrisis(GameAction):
    """Submits an authorized decision for one active political crisis."""

    country_tag: str
    crisis_id: str
    decision: str
    decision_reason: str = ""


@dataclass
class ActionSetBattleStrategy(GameAction):
    """
    Updates strategic posture for an active battle.
    """
    battle_id: str
    strategy: str
    country_tag: str = ""
    unit_type: str = "all"


@dataclass
class ActionLaunchStrategicStrike(GameAction):
    """
    Queues a strategic strike against a target region.
    """
    country_tag: str
    target_region_id: int
    weapon_type: str
    target_country_tag: str = ""
    target_mode: str = "military"
    weapon_id: str = ""
    target_object_id: str = ""
    payload_level: int = 0
    authorization_context: str = ""
    origin_region_id: int = 0


@dataclass
class ActionProduceStrategicWeapon(GameAction):
    """Queues production against an existing scenario-configured weapon design."""
    country_tag: str
    weapon_id: str
    quantity: int = 1


@dataclass
class ActionSetForeignOrderAcceptance(GameAction):
    country_tag: str
    is_accepting: bool


@dataclass
class ActionRequestForeignUnitOrder(GameAction):
    buyer_country_tag: str
    seller_country_tag: str
    design_id: str
    quantity: int


@dataclass
class ActionRespondForeignUnitOrder(GameAction):
    order_id: str
    accept: bool


@dataclass
class ActionCancelForeignUnitOrder(GameAction):
    order_id: str


@dataclass
class ActionListUsedUnit(GameAction):
    country_tag: str
    unit_id: str
    price: float = 0.0


@dataclass
class ActionWithdrawUsedUnitListing(GameAction):
    country_tag: str
    listing_id: str


@dataclass
class ActionMarkMessageRead(GameAction):
    """
    Marks a message as read in the player's inbox.
    """
    message_id: str
