from dataclasses import dataclass
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
    Orders a unit to move directly to a target coordinate.
    Routing is intentionally omitted; the military system interpolates progress
    between the source and target geolocation.
    """
    unit_id: str
    target_region_id: int
    target_latitude: Optional[float] = None
    target_longitude: Optional[float] = None

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
class ActionQueueUnitProduction(GameAction):
    """
    Adds a new production order for a country's armed forces.
    """
    country_tag: str
    design_id: str
    quantity: int
    priority: int = 1


@dataclass
class ActionCancelProductionOrder(GameAction):
    """
    Cancels a queued production order.
    """
    order_id: str


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
class ActionSetBattleStrategy(GameAction):
    """
    Updates strategic posture for an active battle.
    """
    battle_id: str
    strategy: str


@dataclass
class ActionLaunchStrategicStrike(GameAction):
    """
    Queues a strategic strike against a target region.
    """
    country_tag: str
    target_region_id: int
    weapon_type: str


@dataclass
class ActionMarkMessageRead(GameAction):
    """
    Marks a message as read in the player's inbox.
    """
    message_id: str
