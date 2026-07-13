from __future__ import annotations

import sys
import os
import multiprocessing as mp
from pathlib import Path
from typing import Sequence

# 1. Setup Python Path
ROOT_DIR = Path(__file__).parent.resolve()
sys.path.append(str(ROOT_DIR))

def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        from src.cli import main as cli_main
        return cli_main(arguments)

    import arcade
    from src.shared.config import GameConfig
    from src.client.window import MainWindow

    try:
        from pyinstrument import Profiler
    except ImportError:
        profiler = None
    else:
        profiler = Profiler()
        profiler.start()

    print("--- OpenPower Engine Initializing ---")
    print(f"Process ID (PID): {os.getpid()}")

    # 3. Initialize Configuration
    config = GameConfig(ROOT_DIR)
    print(f"[Main] Project Root: {config.project_root}")
    print(f"[Main] Active Mods: {config.active_mods}")

    # 4. Start the Window
    # The Window now owns the NavigationService
    window = MainWindow(config)

    # 5. Kickoff
    # window.setup() uses NavigationService to show the LoadingView
    window.setup()

    print("--- Window Created. Handing off to Application Loop. ---")
    try:
        arcade.run()
    finally:
        if profiler is not None:
            profiler.stop()
            if profiler.last_session:
                output_path = ROOT_DIR / "profile_results.html"
                output_path.write_text(profiler.output_html(), encoding="utf-8")
                print(f"Saved {output_path}")
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    mp.set_start_method("spawn", force=True)
    raise SystemExit(main())
