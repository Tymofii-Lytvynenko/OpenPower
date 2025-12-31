```markdown
# OpenPower: Technical Specification & Architecture

**OpenPower** is a modular, data-driven grand strategy engine written in Python. It is designed as a modern, open-source spiritual successor to *SuperPower 2*, emphasizing extreme moddability, performance, and clear architectural separation between the **Engine** (Infrastructure) and the **Game** (Content & Rules).

---

## 1. Technology Stack

* **Language:** Python 3.10+
* **Core Architecture:** [Esper](https://github.com/benmoran/esper) (Entity-Component-System).
* **Rendering:** [Arcade](https://api.arcade.academy/) (OpenGL 3.3+).
* **UI:** [Arcade-ImGui](https://github.com/hbldh/arcade-imgui) (Dear ImGui bindings).
* **Data Configuration:** [rtoml](https://pypi.org/project/rtoml/) (High-performance Rust-based TOML parser/writer).
* **Bulk Data:** CSV/TSV (Standard Library) for large datasets like map provinces.
* **Runtime Database:** [SQLAlchemy](https://www.sqlalchemy.org/) (SQLite) for caching and save games.
* **Localization:** GNU Gettext (`.po` / `.mo` files).

---

## 2. Project Structure

The project strictly separates **Infrastructure** (`src/`) from **Content** (`modules/`).

```text
OpenPower/
├── .venv/                      # Virtual Environment
├── mods.json                   # Load Order Configuration
├── main.py                     # Application Entry Point
├── requirements.txt            # Dependencies
│
├── cache/                      # Ephemeral Runtime Data
│   └── game.db                 # SQLite DB (Generated from TOML/TSV on launch)
├── saves/                      # User Save Files (Serialized SQLite snapshots)
│
├── modules/                    # --- GAMEPLAY CONTENT & LOGIC ---
│   ├── base/                   # The Vanilla Game (treated as a Mod)
│   │   ├── info.json           # Metadata
│   │   ├── assets/             # Binary Media
│   │   │   ├── maps/
│   │   │   │   ├── provinces.png   # Color ID Map (10k x 5k)
│   │   │   │   └── terrain.png     # Visual Texture
│   │   │   └── locales/        # i18n (.po files)
│   │   │
│   │   ├── data/               # STATIC DATA (Source of Truth)
│   │   │   ├── countries/      # TOML files (e.g., ua.toml)
│   │   │   ├── map/
│   │   │   │   └── provinces.tsv   # Bulk Data (ID, Name, Terrain)
│   │   │   └── rules.toml      # Global constants
│   │   │
│   │   └── logic/              # DYNAMIC RULES (Python - Vertical Slicing)
│   │       ├── economy/        # Feature: Economy
│   │       │   ├── components.py   # @dataclass Economy
│   │       │   └── systems.py      # @register_system EconomySystem
│   │       ├── warfare/        # Feature: Warfare
│   │       │   ├── units.py
│   │       │   └── combat.py
│   │       └── main.py         # Logic entry point
│   │
│   └── user_mod/               # Example Mod
│       ├── data/               # Overrides base TOMLs
│       └── logic/              # Injects new mechanics (e.g., Radiation)
│
└── src/                        # --- ENGINE INFRASTRUCTURE (Immutable) ---
    ├── shared/                 # Code shared between Client & Server
    │   ├── commands.py         # Network DTOs (CmdSetTax, CmdMoveUnit)
    │   └── constants.py
    │
    ├── core/                   # [BACKEND] Simulation Server (Headless)
    │   ├── loader.py           # VFS & TOML/TSV Parsing
    │   ├── bootstrap.py        # ETL Pipeline: Merge Mods -> Fill SQLite
    │   ├── mod_loader.py       # Recursively imports `modules/*/logic/*.py`
    │   ├── auto_registry.py    # Decorator logic (@register_system)
    │   ├── i18n.py             # Gettext wrapper
    │   │
    │   ├── network/            # Server Socket & Packet Handling
    │   ├── persistence/        # Save/Load Managers
    │   ├── db/                 # SQLAlchemy Models (Schema)
    │   └── ecs/                # World Manager
    │
    └── client/                 # [FRONTEND] Visualization Client
        ├── window.py           # Main Arcade Window
        ├── ui/                 # ImGui Generators (Reflection-based)
        └── renderers/          # Visual Layers (Map Shader, Units)

```

---

## 3. Data Architecture (The Hybrid Approach)

To balance **Developer Experience (DX)** with **Performance**, we use a hybrid data strategy.

### A. Configuration: TOML (`rtoml`)

Used for: Countries, Units, Technologies, Game Rules.

* **Why:** Human-readable, supports comments (`#`), structured hierarchy (`[section]`).
* **Performance:** `rtoml` (Rust) parses files instantly.
* **Example (`ua.toml`):**
```toml
id = "UA"
name = "Ukraine"
[economy]
budget = 50_000_000
tax_rate = 0.18

```



### B. Bulk Data: TSV/CSV

Used for: Province definitions (10,000+ rows).

* **Why:** TOML/JSON is too verbose for flat arrays. TSV is compact and fast to parse.
* **Example (`provinces.tsv`):**
```tsv
id  name    terrain_id  owner_id
1   Kyiv    plains      UA
2   Lviv    hills       UA

```



### C. Runtime Cache: SQLite

The engine **never** reads TOML/TSV during gameplay.

1. **Bootstrap:** On launch, the engine merges data from all mods.
2. **Hydration:** Merged data is inserted into `cache/game.db` (SQLite).
3. **Gameplay:** ECS entities are created by querying SQLite.

---

## 4. Logic & Modding (Vertical Slicing)

Game logic is organized by **Feature**, not by file type.

### The Logic Folder

Located in `modules/base/logic/`. Contains pure Python code.

* **Components:** Standard Python `dataclasses`.
* **Systems:** `esper.Processor` subclasses.

### Auto-Registration

To avoid manual boilerplate, systems register themselves via decorators.

**File: `modules/base/logic/economy/systems.py**`

```python
from src.core.auto_registry import register_system
import esper

@register_system(priority=10)
class EconomySystem(esper.Processor):
    def process(self, dt):
        # ... logic implementation ...
        pass

```

The `src/core/mod_loader.py` recursively scans the `logic` folders of all active mods and executes these files, triggering the registration.

---

## 5. Networking & State Management

The architecture uses a **Command Pattern** to ensure determinism and separation of concerns.

1. **Input:** Player interacts with UI (e.g., changes tax slider).
2. **Command:** Client generates a DTO: `CmdSetTax(country="UA", val=0.2)`.
3. **Transmission:** Command is serialized and sent to the Server (Localhost or Remote).
4. **Execution:** Server validates the command and updates the ECS Component.
5. **Replication:** Server broadcasts a `WorldUpdate` packet to all clients.
6. **Rendering:** Clients update their local mirror and render the frame.

---

## 6. Rendering Pipeline

Rendering is handled in layers by `Arcade`.

1. **Map Layer:** Renders the terrain texture.
2. **Political Layer (Shader):**
* Uses a Fragment Shader and the `provinces.png` (Color ID Map).
* Lookups the Province ID from the pixel color.
* Lookups the Owner ID from the Province data.
* Renders the Owner's color (with alpha blending).


3. **Object Layer:** Sprites for units/cities.
4. **UI Layer (ImGui):**
* **Reflection UI:** Automatically generates inspector windows by reading the type hints of ECS Components (`budget: float` -> Input Float).



---

## 7. Internationalization (i18n)

* **Format:** GNU Gettext (`.po` files).
* **Workflow:**
* Python code uses `tr("KEY")`.
* Data files (TOML) store keys: `name_key = "UNIT_TANK"`.
* UI resolves keys to text at render time.



---

## 8. Development Workflow

1. **Setup:** `pip install -r requirements.txt`.
2. **Run Game:** `python main.py`.
3. **Run Editor:** `python main.py --editor` (Reuses engine with Editor UI tools).
4. **Create Mod:**
* Create `modules/my_mod/`.
* Add `data/countries/ua.toml` to override base stats.
* Add `logic/my_sys.py` to inject Python code.
* Add to `mods.json`.



```

```
