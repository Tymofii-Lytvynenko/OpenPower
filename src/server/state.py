# This module is intentionally empty.
# GameState, TimeData, and GAME_EPOCH have been relocated to src.shared.state,
# which is importable by all layers (engine, modules, client, server) without
# creating circular dependencies.
#
# All code that previously imported from here must use:
#   from src.shared.state import GameState, TimeData, GAME_EPOCH