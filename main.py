import arcade
import sys
from pathlib import Path

# 1. Setup Python Path
ROOT_DIR = Path(__file__).parent.resolve()
sys.path.append(str(ROOT_DIR))

# 2. Imports
from src.shared.config import GameConfig
# Note: We do NOT import GameSession here anymore.
from src.client.window import MainWindow

def main():
    print("--- OpenPower Engine Initializing ---")
    
    # 3. Initialize Configuration
    config = GameConfig(ROOT_DIR)
    
    print(f"[Main] Project Root: {config.project_root}")
    print(f"[Main] Active Mods: {config.active_mods}")
    
    # --- CRITICAL FIX ---
    # DELETE the line: session = GameSession(config)
    # The session is not created here anymore. It is created by the Loading Screen.
    
    # 4. Start the Window with ONLY config
    window = MainWindow(config)
    
    # 5. Setup & Run
    # This triggers window.setup() -> LoadingView -> StartupTask -> GameSession.create_local()
    window.setup()
    
    print("--- Window Created. Handing off to Loading Screen. ---")
    arcade.run()

if __name__ == "__main__":
    main()