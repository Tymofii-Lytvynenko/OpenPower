import arcade
import sys
from pathlib import Path

# 1. Setup Python Path
# This line ensures that Python can locate the 'src' package regardless of 
# the terminal's current working directory.
ROOT_DIR = Path(__file__).parent.resolve()
sys.path.append(str(ROOT_DIR))

# 2. Imports
# These must be imported AFTER adding ROOT_DIR to sys.path
from src.shared.config import GameConfig
from src.server.session import GameSession
from src.client.window import MainWindow

def main():
    print("--- OpenPower Engine Initializing ---")
    
    # 3. Initialize Configuration
    # The GameConfig class scans the directory structure, loads 'mods.json',
    # and determines where data and assets are located.
    config = GameConfig(ROOT_DIR)
    
    print(f"[Main] Project Root: {config.project_root}")
    print(f"[Main] Active Mods: {config.active_mods}")
    
    # 4. Start the Game Server (Host Session)
    # In a Single-Player environment, the 'Server' runs locally in the same process.
    # This step triggers the DataLoader to read all TSV files into memory (Polars).
    session = GameSession(config)
    
    # 5. Start the Game Client (Window)
    # We inject the 'session' (to access game state) and 'config' (to find assets)
    # into the main window. This completes the dependency injection chain.
    window = MainWindow(session, config)
    
    # 6. Setup & Run
    # Calls the internal setup of the window (which loads the EditorView).
    window.setup()
    
    print("--- Initialization Complete. Starting Game Loop. ---")
    
    # Start the Arcade event loop (blocking call)
    arcade.run()

if __name__ == "__main__":
    main()