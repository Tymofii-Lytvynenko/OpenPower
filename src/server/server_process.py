import time
import multiprocessing as mp
from queue import Empty, Full
from typing import Optional

from src.server.session import GameSession
from src.shared.config import GameConfig


def _drain_queue(queue_obj):
    items = []
    while True:
        try:
            items.append(queue_obj.get_nowait())
        except Empty:
            return items


def run_server_process(
    config_root,
    action_queue: mp.Queue,
    state_queue: mp.Queue,
    progress_queue: mp.Queue,
    save_name: Optional[str] = None,
    shutdown_event: Optional[mp.Event] = None,
    player_tag: Optional[str] = None,
):
    """
    The infinite loop that lives on a separate CPU core.
    Completely isolated from Pyglet/Arcade OpenGL context.
    """
    # 1. Initialize Configuration in this new memory space
    from pathlib import Path

    config = GameConfig(Path(config_root))

    def progress_cb(p: float, text: str):
        progress_queue.put(("PROGRESS", p, text))

    try:
        # Load heavy data without touching client-side graphics state.
        session = GameSession.create_headless(
            config,
            progress_cb=progress_cb,
            save_name=save_name,
            player_tag=player_tag,
        )
        progress_queue.put(("READY", 1.0, "Engine Started"))
    except Exception as e:
        progress_queue.put(("ERROR", 0.0, str(e)))
        return

    # 2. Main Simulation Loop
    target_tps = 10  # 10 Engine ticks per second (100ms per tick)
    tick_time = 1.0 / target_tps
    last_time = time.perf_counter()

    while True:
        if shutdown_event is not None and shutdown_event.is_set():
            return

        current_time = time.perf_counter()
        delta_time = current_time - last_time
        last_time = current_time

        # A. Process Incoming Actions from UI
        for action in _drain_queue(action_queue):
            if action == "SHUTDOWN":
                return  # Graceful exit
            if action == "SAVE_MAP_CHANGES":
                session.save_map_changes()
                continue
            session.receive_action(action)

        # B. Run the Heavy Mathematics
        session.tick(delta_time)

        # C. Serialize and Send State to UI
        ipc_data = session.state.to_ipc()

        # Keep queue lean (drain old frames if UI is lagging behind)
        _drain_queue(state_queue)

        try:
            state_queue.put_nowait(ipc_data)
        except Full:
            pass

        # D. Pace the thread
        elapsed = time.perf_counter() - current_time
        sleep_time = max(0.0, tick_time - elapsed)
        time.sleep(sleep_time)