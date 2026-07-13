import copy
import dataclasses
import polars as pl
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, TYPE_CHECKING

from src.shared.actions import GameAction
from src.shared.determinism import DeterminismState
from src.shared.events import GameEvent, JournalState

if TYPE_CHECKING:
    from src.shared.schema import WorldSchemaRegistry


# The fixed epoch from which all in-game dates are calculated.
# All systems derive the current date by adding 'total_minutes' to this constant.
GAME_EPOCH = datetime(2001, 1, 1, 0, 0)

PERSISTENCE_METADATA_KEY = "persistence"
PERSISTENCE_PERSISTENT = "persistent"
PERSISTENCE_TRANSIENT = "transient"
VALID_PERSISTENCE_POLICIES = frozenset({PERSISTENCE_PERSISTENT, PERSISTENCE_TRANSIENT})
_GAME_STATE_PERSISTENCE_VALIDATED = False


@dataclass
class TimeData:
    """
    A highly optimized data component for time tracking.

    Why separate this from 'globals'?
    1. Performance: Attribute access (.hour) is faster than dict lookup (['hour']).
    2. Type Safety: Provides strict typing for IDEs and static analysis.
    3. Caching: We store pre-calculated integers (year, month, day) so other
       systems don't have to perform expensive datetime math every tick.
    """

    # Source of Truth: Total minutes elapsed since GAME_EPOCH.
    # We use an integer because floating point time eventually loses precision.
    total_minutes: int = 0

    # Cached Human-Readable fields (Updated only when total_minutes changes)
    year: int = 2001
    month: int = 1
    day: int = 1
    hour: int = 0
    minute: int = 0

    # Formatted String (e.g., "2001-01-01 14:30") for UI rendering.
    date_str: str = "2001-01-01 00:00"

    # Simulation State
    speed_level: int = 1
    is_paused: bool = False

    # Internal accumulator for fractional time updates.
    # Not intended for use by other systems.
    _accumulator: float = 0.0


@dataclass
class GameStateCheckpoint:
    tables: Dict[str, pl.DataFrame]
    time: TimeData
    globals: Dict[str, Any]
    system_state: Dict[str, Dict[str, Any]]
    determinism: DeterminismState
    journal: JournalState
    events: List["GameEvent"]
    current_actions: List["GameAction"]
    table_revisions: Dict[str, int]


@dataclass
class GameState:
    """
    The central data store for the entire simulation.

    Strictly adheres to Data-Oriented Design: it is a passive container
    that holds the world's state as typed Polars DataFrames. All mutation
    is performed by ECS Systems during a tick; this class has no logic.

    IPC methods (to_ipc / from_ipc) are the only transport boundary.
    """

    # Stores the primary game data (DataFrames).
    # Keys are table names (e.g., 'regions', 'countries').
    tables: Dict[str, pl.DataFrame] = field(
        default_factory=dict,
        metadata={PERSISTENCE_METADATA_KEY: PERSISTENCE_PERSISTENT},
    )

    # Dedicated component for Time state.
    time: TimeData = field(
        default_factory=TimeData,
        metadata={PERSISTENCE_METADATA_KEY: PERSISTENCE_PERSISTENT},
    )

    # Holds other global simulation variables that don't fit into tables.
    globals: Dict[str, Any] = field(
        default_factory=lambda: {
            "tick": 0,
            "game_speed": 1.0,
        },
        metadata={PERSISTENCE_METADATA_KEY: PERSISTENCE_PERSISTENT},
    )

    # Stores checkpointed mutable system internals that must survive save/load.
    system_state: Dict[str, Dict[str, Any]] = field(
        default_factory=dict,
        metadata={PERSISTENCE_METADATA_KEY: PERSISTENCE_PERSISTENT},
    )

    determinism: DeterminismState = field(
        default_factory=DeterminismState,
        metadata={PERSISTENCE_METADATA_KEY: PERSISTENCE_PERSISTENT},
    )

    journal: JournalState = field(
        default_factory=JournalState,
        metadata={PERSISTENCE_METADATA_KEY: PERSISTENCE_PERSISTENT},
    )

    # The transient intra-tick signal bus. Durable gameplay facts are promoted
    # to journal entries by the session after a successful engine step.
    # The Engine clears this list at the start of every tick.
    events: List["GameEvent"] = field(
        default_factory=list,
        metadata={PERSISTENCE_METADATA_KEY: PERSISTENCE_TRANSIENT},
    )

    # Actions received this specific tick.
    # The Engine populates this before systems update.
    current_actions: List["GameAction"] = field(
        default_factory=list,
        metadata={PERSISTENCE_METADATA_KEY: PERSISTENCE_TRANSIENT},
    )

    _schema_registry: Any = field(
        default=None,
        init=False,
        repr=False,
        metadata={PERSISTENCE_METADATA_KEY: PERSISTENCE_TRANSIENT},
    )
    _table_revisions: Dict[str, int] = field(
        default_factory=dict,
        init=False,
        repr=False,
        metadata={PERSISTENCE_METADATA_KEY: PERSISTENCE_TRANSIENT},
    )

    def __post_init__(self) -> None:
        self._table_revisions = {name: 1 for name in self.tables}

    def bind_schema_registry(self, registry: "WorldSchemaRegistry") -> None:
        self._schema_registry = registry

    @property
    def schema_registry(self) -> "WorldSchemaRegistry | None":
        return self._schema_registry

    @property
    def table_revisions(self) -> Mapping[str, int]:
        return self._table_revisions

    def get_table(self, name: str) -> pl.DataFrame:
        if name not in self.tables:
            raise KeyError(f"Table '{name}' not found in GameState.")
        return self.tables[name]

    def update_table(self, name: str, df: pl.DataFrame) -> None:
        if not isinstance(df, pl.DataFrame):
            raise TypeError(f"Table '{name}' must be a Polars DataFrame.")
        if self._schema_registry is not None:
            df = self._schema_registry.normalize(name, df)
        self.tables[name] = df
        self._table_revisions[name] = self._table_revisions.get(name, 0) + 1

    def remove_table(self, name: str) -> None:
        self.tables.pop(name, None)
        self._table_revisions[name] = self._table_revisions.get(name, 0) + 1

    def create_checkpoint(self) -> GameStateCheckpoint:
        # Polars frames are immutable and copy-on-write, so retaining frame
        # references is sufficient while mutable Python containers are copied.
        return GameStateCheckpoint(
            tables=dict(self.tables),
            time=copy.deepcopy(self.time),
            globals=copy.deepcopy(self.globals),
            system_state=copy.deepcopy(self.system_state),
            determinism=copy.deepcopy(self.determinism),
            journal=copy.deepcopy(self.journal),
            events=copy.deepcopy(self.events),
            current_actions=list(self.current_actions),
            table_revisions=dict(self._table_revisions),
        )

    def restore_checkpoint(self, checkpoint: GameStateCheckpoint) -> None:
        self.tables = dict(checkpoint.tables)
        self.time = checkpoint.time
        self.globals = checkpoint.globals
        self.system_state = checkpoint.system_state
        self.determinism = checkpoint.determinism
        self.journal = checkpoint.journal
        self.events = checkpoint.events
        self.current_actions = checkpoint.current_actions
        self._table_revisions = checkpoint.table_revisions

    # --- MULTIPROCESSING IPC METHODS ---

    def to_ipc(self) -> dict[str, Any]:
        from src.shared.snapshots import StateSnapshotEncoder

        return StateSnapshotEncoder().encode(self, force_full=True)

    @classmethod
    def from_ipc(cls, data: dict[str, Any]) -> "GameState":
        from src.shared.snapshots import StateSnapshotDecoder

        return StateSnapshotDecoder().decode(data)


def validate_game_state_persistence_contract() -> None:
    global _GAME_STATE_PERSISTENCE_VALIDATED
    if _GAME_STATE_PERSISTENCE_VALIDATED:
        return

    missing_fields: list[str] = []
    invalid_fields: dict[str, Any] = {}
    for game_state_field in dataclasses.fields(GameState):
        policy = game_state_field.metadata.get(PERSISTENCE_METADATA_KEY)
        if policy is None:
            missing_fields.append(game_state_field.name)
        elif policy not in VALID_PERSISTENCE_POLICIES:
            invalid_fields[game_state_field.name] = policy

    if missing_fields or invalid_fields:
        details: list[str] = []
        if missing_fields:
            details.append(f"missing metadata for fields: {sorted(missing_fields)}")
        if invalid_fields:
            details.append(f"invalid policies: {invalid_fields}")
        raise RuntimeError("GameState persistence contract is incomplete: " + "; ".join(details))

    _GAME_STATE_PERSISTENCE_VALIDATED = True


def _state_fields_by_policy(policy: str) -> tuple[dataclasses.Field[Any], ...]:
    validate_game_state_persistence_contract()
    return tuple(
        game_state_field
        for game_state_field in dataclasses.fields(GameState)
        if game_state_field.metadata[PERSISTENCE_METADATA_KEY] == policy
    )


def persistent_state_fields() -> tuple[dataclasses.Field[Any], ...]:
    return _state_fields_by_policy(PERSISTENCE_PERSISTENT)


def persistent_state_field_names() -> tuple[str, ...]:
    return tuple(game_state_field.name for game_state_field in persistent_state_fields())


def transient_state_fields() -> tuple[dataclasses.Field[Any], ...]:
    return _state_fields_by_policy(PERSISTENCE_TRANSIENT)


validate_game_state_persistence_contract()
