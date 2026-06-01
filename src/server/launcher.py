"""
Server process launcher factory.

This module is the single place where the background simulation process is
spawned. It lives in the server layer, so importing run_server_process and
multiprocessing infrastructure is completely compliant with the layer rules.

The client layer (ClientSessionProxy) receives fully constructed IPC channels
from here and never needs to know how the process is started.
"""

import multiprocessing as mp
from typing import Optional

from src.shared.config import GameConfig
from src.core.map_data import RegionMapData
from src.server.server_process import run_server_process


def _resolve_map_path(config: GameConfig):
    """Finds the technical region map image used for UI pixel-picking."""
    for data_dir in config.get_data_dirs():
        candidate = data_dir / "regions" / "regions.png"
        if candidate.exists():
            return candidate

    # Fall back to the asset path defined in config
    return config.get_asset_path("map/regions.png")


def spawn_local_server(
    config: GameConfig,
    save_name: Optional[str] = None,
) -> "ClientSessionProxy":
    """
    Spawns a background simulation process and returns a ready-to-use proxy.

    This is the canonical entry point for starting or loading a local game.
    Both MainWindow and all loading tasks must call this function instead of
    constructing ClientSessionProxy directly.

    Args:
        config:    Active game configuration (used for path resolution and
                   forwarding to the server process).
        save_name: Name of an existing save slot to load, or None to start
                   a fresh game from the initial static data.

    Returns:
        A ClientSessionProxy wired to the new process via IPC queues.
        The caller is responsible for polling progress_queue until 'READY'.
    """
    # Lazy import to keep circular-import risk zero — ClientSessionProxy
    # lives in client but we return it here for convenience; it holds no
    # server knowledge itself after this refactor.
    from src.client.client_session import ClientSessionProxy

    # Create IPC communication channels
    action_queue: mp.Queue = mp.Queue()
    state_queue: mp.Queue = mp.Queue()
    progress_queue: mp.Queue = mp.Queue()

    # Spawn the background CPU core (headless, no OpenGL context)
    process = mp.Process(
        target=run_server_process,
        args=(str(config.project_root), action_queue, state_queue, progress_queue, save_name),
        daemon=True,  # Ensures process dies if the window is closed abruptly
    )
    process.start()

    # Load the region map image for the client-side pixel-picking renderer.
    # This runs in the main process because RegionMapData uses OpenCV/NumPy
    # which is safe to call here (no OpenGL context required).
    map_path = _resolve_map_path(config)
    print(f"[Launcher] Loading UI map data from: {map_path}")
    map_data = RegionMapData(str(map_path))

    return ClientSessionProxy(
        map_data=map_data,
        action_queue=action_queue,
        state_queue=state_queue,
        progress_queue=progress_queue,
        process=process,
    )
