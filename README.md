# OpenPower: Technical Specification

**OpenPower** is an open-source, data-driven geopolitical grand strategy simulator engine written in pure Python. It is designed as a modern, highly moddable spiritual successor to titles like *SuperPower 2*, utilizing an Entity-Component-System (ECS) architecture.

## 1. Technology Stack

* **Language:** Python 3.10+
* **Core Logic:** [Esper](https://github.com/benmoran/esper) (ECS - Entity Component System)
* **Rendering:** [Arcade](https://api.arcade.academy/) (OpenGL 3.3+ wrapper)
* **User Interface:** [Arcade-ImGui](https://github.com/hbldh/arcade-imgui) (Dear ImGui implementation)
* **Data & Persistence:** [SQLAlchemy](https://www.sqlalchemy.org/) (SQLite)
* **Image Processing:** Pillow (PIL) for map data analysis.

---

## 2. Architectural Philosophy

OpenPower follows a **"Modding First"** and **"Data-Driven"** philosophy. The engine (`src/`) is entirely agnostic of the gameplay rules. The actual game (taxes, tanks, diplomacy) is implemented as the "Base Mod" (`modules/base/`).

### Core Pillars
1.  **Vertical Slicing:** Code is organized by **Feature** (e.g., Economy, War), not by file type. A single folder contains the Components, Systems, and Data definitions for a specific mechanic.
2.  **Server-Authoritative:** The simulation logic runs headless (server-side logic). The client sends **Commands** and receives **State Updates**. Singleplayer is simply a local server and client running in parallel.
3.  **Ephemeral Database:** The runtime database (`cache/game.db`) is rebuilt from JSON source files at every launch. Modders edit JSONs; the engine plays with SQL.

---

## 3. Project Structure

```text
OpenPower/
├── .venv/                      # Python Virtual Environment
├── mods.json                   # Load Order Config (e.g., ["base", "user_mod"])
├── main.py                     # Entry Point
│
├── cache/                      # Runtime generated files
│   └── game.db                 # SQLite DB (Result of merged JSONs)
├── saves/                      # User save files (Serialized ECS snapshots)
│
├── modules/                    # --- CONTENT & GAMEPLAY LOGIC ---
│   ├── base/                   # The Vanilla Game
│   │   ├── info.json           # Metadata
│   │   ├── assets/             # Raw media (PNG, WAV)
│   │   │   └── maps/provinces.png  # Color ID Map (10000x5000)
│   │   ├── data/               # STATIC DATA (JSON)
│   │   │   ├── countries/      # Country definitions
│   │   │   └── resources.json  # Resource definitions
│   │   └── logic/              # DYNAMIC RULES (Python)
│   │       ├── economy/        # Economy Module
│   │       │   ├── components.py
│   │       │   └── systems.py
│   │       └── warfare/        # Warfare Module
│   │           └── units.py
│   │
│   └── user_mod/               # Example User Mod
│       ├── data/               # Overrides base JSONs
│       └── logic/              # Injects new Systems
│
└── src/                        # --- ENGINE INFRASTRUCTURE ---
    ├── shared/                 # Shared Code (Client & Server)
    │   ├── commands.py         # Network DTOs (Data Transfer Objects)
    │   └── constants.py
    │
    ├── core/                   # [BACKEND] Simulation Engine
    │   ├── resources.py        # Virtual File System (VFS)
    │   ├── mod_loader.py       # Python Logic Injector
    │   ├── bootstrap.py        # ETL: JSON -> SQLite Pipeline
    │   ├── auto_registry.py    # Decorators (@register_system)
    │   ├── ecs/                # Esper Wrapper
    │   ├── db/                 # SQLAlchemy Models
    │   ├── network/            # Server Socket Logic
    │   └── persistence/        # Save/Load Manager
    │
    └── client/                 # [FRONTEND] Visualization
        ├── window.py           # Main Arcade Window
        ├── ui/                 # ImGui Generators (Reflection UI)
        └── renderers/          # Visual Layers (Map, Units)

```

---

## 4. Data Pipeline (The Boot Sequence)

To avoid "SQL Hell" for modders, the engine uses a **JSON-to-Database** pipeline.

1. **VFS Resolution:** The `ResourceManager` reads `mods.json` to determine the load order.
2. **Deep Merge:** The `Bootstrap` script scans `modules/*/data/`. If `user_mod` has a file that exists in `base`, the dictionaries are merged (User Mod overrides Base).
3. **Hydration:** The merged data is inserted into an in-memory or cached SQLite database using SQLAlchemy models.
4. **ECS Instantiation:** The `WorldManager` queries the SQLite DB to create Entity-Component relationships in RAM.

**Flow:**
`JSON Files (Mods)` -> `Deep Merge` -> `SQLite Cache` -> `ECS RAM (Live Game)`

---

## 5. Logic Injection & Modding

Logic is handled via **Python Injection**. The engine recursively scans `modules/*/logic/` for Python scripts.

### The Auto-Registry Pattern

To minimize boilerplate, we use decorators to register systems automatically.

**Example: `modules/base/logic/economy/systems.py**`

```python
from src.core.auto_registry import register_system
import esper

@register_system(priority=100)
class EconomySystem(esper.Processor):
    def process(self, dt):
        # Logic implementation
        pass

```

The `mod_loader.py` imports this file, and the decorator adds the class to the Engine's initialization queue.

---

## 6. Rendering Architecture

Rendering is separated into distinct layers handled by `Arcade`.

1. **Map Layer (Terrain):** Standard texture rendering.
2. **Political Layer (Shaders):** A fragment shader utilizes a `provinces.png` (Color ID Map). It samples the pixel color, converts it to a Region ID, checks the ECS for the region's owner, and renders the owner's color.
3. **UI Layer (ImGui):**
* **Reflection UI:** The UI generator inspects Python `dataclasses` (Components). If a component has a field `budget: float`, the UI automatically renders an input field.
* No manual UI coding is required for standard data.



---

## 7. Networking & State Management

The game utilizes a **Command Pattern** for state changes.

### Command Flow

1. **Input:** Player interacts with UI (e.g., changes Tax Rate).
2. **Command:** Client sends a `SetTaxCommand(country_id="UA", value=0.2)` DTO.
3. **Server Validation:** Server checks if the player owns "UA".
4. **Execution:** Server updates the ECS Component.
5. **Replication:** Server broadcasts a `WorldStateUpdate` packet to all clients.

### Persistence (Saves)

Saving is essentially serializing the current ECS state back into a database format.

* **Save:** ECS RAM -> `saves/savegame.db`
* **Load:** `saves/savegame.db` -> ECS RAM

---

## 8. Getting Started

### Prerequisites

* Python 3.10+
* Pip

### Installation

1. Clone the repository.
2. Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

```


3. Install dependencies:
```bash
pip install -r requirements.txt

```


4. Run the engine:
```bash
python main.py

```



```

```