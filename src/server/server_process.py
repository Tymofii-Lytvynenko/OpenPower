import time
import multiprocessing as mp
from src.server.session import GameSession
from src.shared.config import GameConfig

def run_server_process(config_root, action_queue: mp.Queue, state_queue: mp.Queue, progress_queue: mp.Queue):
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
        # Load heavy data
        session = GameSession.create_local(config, progress_cb=progress_cb)
        progress_queue.put(("READY", 1.0, "Engine Started"))
    except Exception as e:
        progress_queue.put(("ERROR", 0.0, str(e)))
        return

    # 2. Main Simulation Loop
    target_tps = 10  # 10 Engine ticks per second (100ms per tick)
    tick_time = 1.0 / target_tps
    last_time = time.perf_counter()

    while True:
        current_time = time.perf_counter()
        delta_time = current_time - last_time
        last_time = current_time

        # A. Process Incoming Actions from UI
        while not action_queue.empty():
            try:
                action = action_queue.get_nowait()
                if action == "SHUTDOWN":
                    return # Graceful exit
                session.receive_action(action)
            except Exception:
                pass

        # B. Run the Heavy Mathematics
        session.tick(delta_time)

        # C. Serialize and Send State to UI
        ipc_data = session.state.to_ipc()
        
        # Keep queue lean (drain old frames if UI is lagging behind)
        while not state_queue.empty():
            try:
                state_queue.get_nowait()
            except Exception:
                pass
                
        state_queue.put(ipc_data)

        # D. Pace the thread
        elapsed = time.perf_counter() - current_time
        sleep_time = max(0.0, tick_time - elapsed)
        time.sleep(sleep_time)