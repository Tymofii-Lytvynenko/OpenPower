from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Callable, Optional

from src.core.map_data import RegionMapData
from src.engine.command_pipeline import CommandPipeline
from src.engine.journal import DomainEventJournal
from src.engine.mod_manager import ModManager
from src.engine.simulator import Engine
from src.server.command_policy import authorize_country_scope, validate_finite_payload
from src.server.io.data_export_manager import DataExporter
from src.server.io.data_load_manager import DataLoader
from src.server.io.save_writer import SaveWriter
from src.shared.actions import ActionSaveGame, GameAction
from src.shared.commands import CommandEnvelope, CommandStatus, command_id_for
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
        initial_state = loader.load_save(save_name) if save_name else loader.load_initial_state()
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
    ) -> "GameSession":
        return cls.create_local(
            config,
            progress_cb=progress_cb,
            save_name=save_name,
            load_map_data=False,
            player_tag=player_tag,
            random_seed=random_seed,
        )

    @staticmethod
    def _load_map_data(config: GameConfig) -> RegionMapData:
        for data_dir in config.get_data_dirs():
            candidate = data_dir / "regions" / "regions.png"
            if candidate.exists():
                return RegionMapData(str(candidate))
        return RegionMapData(str(config.get_asset_path("map/regions.png")))

    def tick(self, delta_time: float) -> None:
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

        for command in save_commands:
            self.engine.snapshot_system_state(self.state)
            saved = SaveWriter(self.config).save_game(self.state, command.action.save_name)
            status = CommandStatus.EXECUTED if saved else CommandStatus.FAILED
            result = self.command_pipeline.result(
                command,
                int(self.state.globals.get("tick", 0)),
                status,
                "" if saved else "save_failed",
                "" if saved else f"Could not save '{command.action.save_name}'.",
            )
            self.state.journal.append_command_result(result.to_record())

        if not simulation_commands and delta_time <= 0:
            self.state.current_actions = []
            return

        step_result = self.engine.step(
            self.state,
            [command.action for command in simulation_commands],
            float(delta_time),
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
