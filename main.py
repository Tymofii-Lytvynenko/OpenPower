import arcade
import sys
import os
from pathlib import Path
from pyinstrument import Profiler

# 1. Setup Python Path
ROOT_DIR = Path(__file__).parent.resolve()
sys.path.append(str(ROOT_DIR))

# 2. Imports
from src.shared.config import GameConfig
from src.client.window import MainWindow

def main():
    # Performance Profiling (Optional: Can be toggleable via args)
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
        profiler.stop()
        
        # Save profile only if meaningful data exists
        if profiler.last_session:
            output_path = "profile_results.html"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(profiler.output_html())
            print(f"✅ Saved {output_path}")

if __name__ == "__main__":
    main()