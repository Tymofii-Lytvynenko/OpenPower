from __future__ import annotations

from collections import defaultdict
from typing import Callable, Optional

from src.core.paths import resolve_region_map_path
from src.core.map_data import RegionMapData
from src.engine.command_pipeline import CommandPipeline
from src.engine.journal import DomainEventJournal
from src.engine.mod_manager import ModManager
from src.engine.simulator import Engine
from src.server.command_policy import authorize_country_scope, validate_finite_payload
from src.server.io.data_export_manager import DataExporter
from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.server.state_migrations import (
    migrate_political_state,
    migrate_tactical_combat_state,
    validate_tactical_combat_state,
)
from src.shared.actions import ActionSaveGame, GameAction
from src.shared.commands import (
    COMMAND_PROTOCOL_ERROR,
    LOCAL_SESSION_ACTOR_ID,
    CommandEnvelope,
    CommandStatus,
    command_id_for,
)
from src.shared.config import GameConfig
from src.shared.schema import WorldSchemaRegistry
from src.shared.state import GameState


class GameSession:
    """Authoritative composition root for state, systems, commands, and persistence."""

    def __init__(
        self,
        config: GameConfig,
        loader: DataLoader | None,
        exporter: DataExporter | None,
        engine: Engine,
        map_data: RegionMapData | None,
        initial_state: GameState,
        player_tag: str | None = None,
        schema_registry: WorldSchemaRegistry | None = None,
    ):
        self.config = config
        self.root_dir = config.project_root
        self.loader = loader
        self.exporter = exporter
        self.engine = engine
        self.map_data = map_data
        self.schemas = schema_registry or WorldSchemaRegistry()
        self.state = initial_state

        # Repair additive tactical columns before validation and schema capture;
        # otherwise a legacy battle row would be frozen with nullable anchors.
        migrate_tactical_combat_state(self.state)
        migrate_political_state(self.state, self.schemas)
        migration_issues = validate_tactical_combat_state(self.state)
        if migration_issues:
            raise RuntimeError(
                "Tactical combat state migration failed: " + ", ".join(migration_issues)
            )

        self.schemas.capture_state(self.state)
        self.schemas.ensure_state(self.state)
        schema_issues = self.schemas.validate_state(self.state)
        if schema_issues:
            details = "; ".join(
                f"{issue.table}:{issue.code}" for issue in schema_issues
            )
            raise RuntimeError(f"Session state violates world schemas: {details}")

        if player_tag:
            self.state.globals["player_tag"] = player_tag
        self.player_tag = self.state.globals.get("player_tag")
        self.engine.restore_system_state(self.state)
        self.engine.snapshot_system_state(self.state)

        initial_sequences: dict[str, int] = defaultdict(int)
        for result in self.state.journal.command_results:
            # Protocol rejections never consume a sequence in the live pipeline.
            if result.get("code") == COMMAND_PROTOCOL_ERROR:
                continue
            actor = str(result.get("actor_id", ""))
            if actor:
                initial_sequences[actor] = max(
                    initial_sequences[actor], int(result.get("sequence", 0))
                )
        self._next_sequence = defaultdict(int, initial_sequences)
        self.command_pipeline = CommandPipeline(
            validators=(
                validate_finite_payload,
                authorize_country_scope,
                self._validate_command_route,
            ),
            initial_sequences=dict(initial_sequences),
        )
        self.domain_journal = DomainEventJournal()

        print("[GameSession] Session initialized successfully.")

    @classmethod
    def create_local(
        cls,
        config: GameConfig,
        progress_cb: Optional[Callable[[float, str], None]] = None,
        save_name: Optional[str] = None,
        load_map_data: bool = True,
        player_tag: str | None = None,
        random_seed: int | None = 1,
        *,
        player_party_id: str | None = None,
    ) -> "GameSession":
        def report(progress: float, text: str) -> None:
            if progress_cb:
                progress_cb(progress, text)

        report(0.1, "Server: Scanning and resolving mods...")
        mod_manager = ModManager(config)
        active_mods = mod_manager.resolve_load_order()
        config.active_mods = [mod.id for mod in active_mods]
        runtime = mod_manager.load_runtime()

        report(0.2, "Server: Initializing IO subsystems...")
        loader = DataLoader(
            config,
            migrations=runtime.migrations,
            schema_registry=runtime.schemas,
        )
        exporter = DataExporter(config)

        report(0.3, "Server: Loading world database...")
        is_new_game = not bool(save_name)
        initial_state = loader.load_initial_state() if is_new_game else loader.load_save(save_name)
        if is_new_game:
            initial_state.globals["history_start_seed_pending"] = True
            # Distinguish a fresh world waiting for army inputs from legacy saves
            # whose intentionally empty armies must not be recreated.
            initial_state.globals.setdefault("military_initial_units_created", False)
            # A fresh local host owns scenario settings unless the world assigns them explicitly.
            initial_state.globals.setdefault("scenario_admin_id", LOCAL_SESSION_ACTOR_ID)
            if player_tag and player_party_id:
                initial_state.globals["player_party_id"] = player_party_id.strip()
        if save_name is None and random_seed is not None:
            initial_state.determinism.reset(random_seed)

        report(0.6, "Server: Preparing simulation runtime...")
        map_data = cls._load_map_data(config) if load_map_data else None

        report(0.8, "Server: Registering game systems...")
        engine = Engine(dev_mode=config.dev_mode)
        engine.register_systems(runtime.systems)

        report(1.0, "Server: Ready.")
        return cls(
            config,
            loader,
            exporter,
            engine,
            map_data,
            initial_state,
            player_tag=player_tag,
            schema_registry=runtime.schemas,
        )

    @classmethod
    def create_headless(
        cls,
        config: GameConfig,
        progress_cb: Optional[Callable[[float, str], None]] = None,
        save_name: Optional[str] = None,
        player_tag: str | None = None,
        random_seed: int | None = 1,
        *,
        player_party_id: str | None = None,
    ) -> "GameSession":
        return cls.create_local(
            config,
            progress_cb=progress_cb,
            save_name=save_name,
            load_map_data=False,
            player_tag=player_tag,
            random_seed=random_seed,
            player_party_id=player_party_id,
        )

    @staticmethod
    def _load_map_data(config: GameConfig) -> RegionMapData:
        return RegionMapData(str(resolve_region_map_path(config)))

    def tick(self, delta_time: float) -> None:
        telemetry = getattr(self.engine, "telemetry", None)
        if telemetry is None or not telemetry.enabled:
            self._tick(delta_time)
            return
        telemetry.increment("simulation.ticks")
        with telemetry.measure("simulation.tick.total_ms"):
            self._tick(delta_time)

    def _tick(self, delta_time: float) -> None:
        next_tick = int(self.state.globals.get("tick", 0)) + 1
        prepared = self.command_pipeline.prepare(self.state, next_tick)
        for result in prepared.rejected:
            self.state.journal.append_command_result(result.to_record())

        save_commands = tuple(
            command for command in prepared.ready if isinstance(command.action, ActionSaveGame)
        )
        simulation_commands = tuple(
            command for command in prepared.ready if not isinstance(command.action, ActionSaveGame)
        )

        simulation_succeeded = self._run_simulation_step(simulation_commands, delta_time)
        if save_commands and not simulation_commands and delta_time <= 0:
            self.engine.snapshot_system_state(self.state)

        # Save the published tick, including gameplay commands received alongside the save request.
        for command in save_commands:
            saved = simulation_succeeded and SaveWriter(self.config).save_game(
                self.state, command.action.save_name
            )
            failure_message = ""
            if not simulation_succeeded:
                failure_message = "Could not save because the simulation step failed."
            elif not saved:
                failure_message = f"Could not save '{command.action.save_name}'."
            status = CommandStatus.EXECUTED if saved else CommandStatus.FAILED
            result = self.command_pipeline.result(
                command,
                int(self.state.globals.get("tick", 0)),
                status,
                "" if saved else "save_failed",
                failure_message,
            )
            self.state.journal.append_command_result(result.to_record())

    def _run_simulation_step(
        self, simulation_commands: tuple[CommandEnvelope, ...], delta_time: float
    ) -> bool:
        if not simulation_commands and delta_time <= 0:
            self.state.current_actions = []
            return True

        telemetry = getattr(self.engine, "telemetry", None)
        if telemetry and telemetry.enabled:
            with telemetry.measure("simulation.engine_step_ms"):
                step_result = self.engine.step(
                    self.state, [command.action for command in simulation_commands], float(delta_time)
                )
        else:
            step_result = self.engine.step(
                self.state, [command.action for command in simulation_commands], float(delta_time)
            )
        status = CommandStatus.EXECUTED if step_result.success else CommandStatus.FAILED
        failure_message = (
            step_result.failures[0].error_message if step_result.failures else ""
        )
        for command in simulation_commands:
            result = self.command_pipeline.result(
                command,
                step_result.tick,
                status,
                "" if step_result.success else "simulation_step_failed",
                failure_message,
            )
            self.state.journal.append_command_result(result.to_record())

        self.domain_journal.capture(self.state)
        self.engine.snapshot_system_state(self.state)
        self.state.current_actions = []
        return step_result.success

    def receive_action(self, action: GameAction) -> str:
        actor_id = str(action.player_id)
        self._next_sequence[actor_id] += 1
        command_id = command_id_for(actor_id, self._next_sequence[actor_id])
        self.receive_command(
            CommandEnvelope(
                command_id=command_id,
                actor_id=actor_id,
                sequence=self._next_sequence[actor_id],
                action=action,
            )
        )
        return command_id

    def receive_command(self, command: CommandEnvelope) -> None:
        self.command_pipeline.submit(command)

    def _validate_command_route(
        self,
        command: CommandEnvelope,
        state: GameState,
    ) -> str | None:
        if isinstance(command.action, ActionSaveGame):
            return None
        if type(command.action) not in self.engine.handled_action_types:
            return f"No simulation system handles {type(command.action).__name__}."
        return None

    def get_state_snapshot(self) -> GameState:
        return self.state

    def save_map_changes(self) -> None:
        if self.exporter is None:
            raise RuntimeError("This session has no data exporter.")
        self.exporter.save_regions(self.state)
