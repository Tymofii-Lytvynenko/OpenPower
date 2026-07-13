from __future__ import annotations

from src.server.io.data_load_manager import DataLoader
from src.shared.config import GameConfig
from src.shared.migrations import MigrationRegistry
from src.shared.schema import WorldSchemaRegistry
from src.shared.state import GameState


class SaveStateLoader:
    """Focused save facade backed by the canonical DataLoader implementation."""

    def __init__(
        self,
        config: GameConfig,
        migrations: MigrationRegistry | None = None,
        schema_registry: WorldSchemaRegistry | None = None,
    ):
        self._loader = DataLoader(
            config,
            migrations=migrations,
            schema_registry=schema_registry,
        )

    def load(self, save_name: str) -> GameState:
        return self._loader.load_save(save_name)
