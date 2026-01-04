# OpenPower: Technical Specification & Architecture

**OpenPower** is a modular, data-driven grand strategy engine written in Python. It is designed as a modern, open-source spiritual successor to *SuperPower 2*.

The engine moves away from traditional Object-Oriented Programming (OOP) and Entity-Component-Systems (ECS) in favor of **Data-Oriented Design (DOD)**. By leveraging **Polars**, the engine processes game state as massive in-memory tables, allowing for vectorized performance that rivals C++ engines while maintaining the moddability of Python.

---

## 1. Technology Stack

* **Language:** Python 3.10+
* **Core Engine:** [Polars](https://pola.rs/) (High-performance DataFrames, written in Rust).
* **Rendering:** [Arcade](https://api.arcade.academy/) (OpenGL 3.3+).
* **UI:** [imgui-bundle](https://github.com/pthom/imgui_bundle) (Dear ImGui bindings).
* **Data Configuration:** [rtoml](https://pypi.org/project/rtoml/) (Fastest Rust-based TOML parser).
* **Bulk Data:** TSV/CSV (Standard Library) for map regions and population grids.
* **Serialization:** [Apache Arrow](https://arrow.apache.org/) (via Polars IPC) for instant Save/Load.

---

## 2. Project Structure

The project follows a **Composition over Inheritance** philosophy. Data (`state`) is strictly separated from Behavior (`pipeline`).

```text
OpenPower/
├── .venv/                      # Virtual Environment
├── mods.json                   # Load Order Configuration
├── main.py                     # Application Entry Point
├── cache/                      # Runtime fast-load cache
│
├── modules/                    # --- GAMEPLAY CONTENT & LOGIC ---
│   ├── base/
│   │   ├── assets/             # Binary Media (Textures, Audio)
│   │   │   └── map/
│   │   │       └── regions.png # Color ID Map
│   │   │
│   │   ├── data/               # SOURCE DATA (Human Readable)
│   │   │   ├── countries/      # TOML files (e.g., USA.toml)
│   │   │   ├── map/
│   │   │   │   └── regions.tsv # Static Region Definitions (ID, Terrain)
│   │   │   └── scenarios/
│   │   │       └── 2025/       # Scenario Data
│   │   │           └── pop.tsv # Dynamic Population Data
│   │   │
│   │   └── logic/              # BEHAVIOR (Pure Python Functions)
│   │       ├── economy.py      # def system_tax_income(state)
│   │       ├── demography.py   # def system_growth(state)
│   │       └── military.py
│
└── src/                        # --- ENGINE INFRASTRUCTURE ---
    ├── server/
    │   ├── state/              # [DATA LAYER]
    │   │   ├── store.py        # GameState class (Dict of DataFrames)
    │   │   └── schema.py       # Column type definitions
    │   │
    │   ├── io/                 # [INPUT/OUTPUT LAYER]
    │   │   ├── loader.py       # TOML/TSV -> Polars DataFrame
    │   │   ├── writer.py       # DataFrame -> .arrow (Save Game)
    │   │   └── resources.py    # VFS (Virtual File System)
    │   │
    │   └── pipeline/           # [EXECUTION LAYER]
    │       ├── runner.py       # Main Loop (Tick Orchestrator)
    │       └── registry.py     # Auto-discovery of logic functions
    │
    └── client/                 # [VISUALIZATION LAYER]
        ├── map_view.py         # Arcade Window & Shader Logic
        ├── bridge.py           # Polars -> Numpy (Zero-copy GPU transfer)
        └── ui/                 # ImGui Interface

```

---

## 3. Data Architecture (The "Compiler" Approach)

We treat game data as a compilation process: **Human Source -> Machine State**.

### A. Source: TOML & TSV (For Humans)

Optimized for readability and version control (Git).

1. **Entities (Countries, Units):** **TOML** (`rtoml`).
* *Why:* Structured, hierarchical, supports comments.
* *Example:* `ua.toml` defines budget, tags, and political structure.


2. **Arrays (Regions, Population):** **TSV** (Tab-Separated Values).
* *Why:* Easy to edit in Excel/Spreadsheets. Compact for 10,000+ rows.
* *Example:* `regions.tsv` contains `id`, `terrain_id`, `owner_id`.



### B. Runtime: Polars DataFrames (For Logic)

Optimized for SIMD vectorization and CPU cache locality.

* **Initialization:** On launch, the `loader.py` reads all TOML/TSV files from all active mods.
* **Compilation:** It converts them into `pl.DataFrame` objects stored in `GameState`.
* **Indexing:** Data is processed by Columns, not Rows.

### C. Storage: Apache Arrow (For Speed)

* **Save Game:** The engine dumps the in-memory DataFrames directly to disk using Polars IPC (`.arrow`).
* **Speed:** Saving/Loading takes milliseconds because no parsing is required (memory dump).

---

## 4. Logic & Modding (The Pipeline)

Instead of "Systems" in an ECS that loop over entities, we use **Pipeline Functions** that transform tables.

### Composition via Joins

Logic is composed by joining tables. If a mod adds "Radiation", it does not modify the `Region` class. It simply adds a `radiation` table and joins it during calculation.

**Example System (`modules/base/logic/economy.py`):**

```python
import polars as pl

def system_calculate_taxes(state):
    # 1. Access Tables
    regions = state.get_table("regions")
    countries = state.get_table("countries")

    # 2. Vectorized Aggregation (No Python Loops!)
    # SQL equivalent: SELECT owner_id, SUM(pop * tax) ... GROUP BY owner_id
    income_agg = (
        regions
        .group_by("owner_id")
        .agg((pl.col("population") * 0.1).sum().alias("tax_income"))
    )

    # 3. Update State via Join
    state.tables["countries"] = (
        countries
        .join(income_agg, left_on="id", right_on="owner_id", how="left")
        .with_columns(
            (pl.col("budget") + pl.col("tax_income").fill_null(0)).alias("budget")
        )
        .drop("tax_income")
    )

```

---

## 5. Rendering Pipeline (Zero-Copy)

Rendering is decoupled from simulation. The visual layer reads the DataFrames and converts them to GPU buffers without iterating in Python.

1. **Map Layer:**
* `regions.png` provides the geometry (Color ID map).
* A Fragment Shader looks up the pixel color.
* **The Bridge:** `client/bridge.py` extracts the `owner_id` column from the `regions` DataFrame, converts it to a `numpy` array (zero-copy), and uploads it to a Texture Buffer (TBO).
* The Shader uses the TBO to color the region based on the owner's color.


2. **UI Layer:**
* ImGUI bundle reads directly from Polars DataFrames to render tables and inspector windows.



---

## 6. Development Workflow

1. **Setup:** `pip install -r requirements.txt`.
2. **Run Game:** `python main.py`.
3. **Edit Map:**
* Open `modules/base/data/map/regions.tsv` in **LibreOffice or something else**.
* Change terrain/ownership.
* Restart game.


4. **Create Mod:**
* Create `modules/my_mod/data/countries/NCR.toml`.
* The engine automatically detects, loads, and merges it into the `countries` DataFrame.