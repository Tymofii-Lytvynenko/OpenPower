# OpenPower Engine

> **⚠️ NOTE: Work in Progress**
> This document describes the **target architecture** for version 1.0.
> Not all features listed below (specifically networking and full modding support) are fully implemented yet.
> Current status: **Single-player prototype phase.**

**OpenPower** is a modern, open-source Grand Strategy Game (GSG) engine built in Python. It leverages **Data-Oriented Design** principles to ensure performance and moddability, using **Polars** for high-speed state management and **Arcade** with **ImGui** for rendering and UI.

The engine is designed to be highly modular, supporting hot-reloadable systems and a robust dependency-based mod loading architecture.

## 🚀 Key Features

* **Data-Oriented Architecture:** Game state is stored in flat **Polars DataFrames** instead of nested objects. Logic is processed via Systems (ECS-lite), enabling SIMD-optimized performance for thousands of regions and countries.
* **Split Client-Server Logic:** Strict separation of concerns. The Client issues `GameAction` commands; the Server (Session) processes them and returns authoritative state snapshots.
* **Advanced Map Rendering:**
    * **Region Atlas:** Custom OpenCV/NumPy pipeline for "Color-as-ID" map processing.
    * **Layering:** Supports Terrain (Artistic), Political (Dynamic Texture Generation), and Overlay (Selection) layers.
* **Professional UI:** Integration of **Dear ImGui** (via `imgui_bundle`) for complex, dockable editor interfaces and smooth game menus.
* **Robust Modding System:**
    * Topological Sort for dependency resolution.
    * Dynamic system loading from `modules/`.
* **Atomic Save System:** Folder-based saves using **Parquet** for heavy data and JSON for metadata, ensuring data integrity and fast IO.

## 📂 Project Structure

```text
OpenPower/
├── modules/                # Game Content & Mods
│   └── base/               # Core game data (countries, regions, systems)
├── saves/                  # User save games (Parquet + JSON)
├── src/
│   ├── client/             # Frontend (Visuals & Input)
│   │   ├── renderers/      # Arcade Sprite & Map Rendering
│   │   ├── services/       # ImGui & Network bridges
│   │   ├── ui/             # UI Composers & Layouts
│   │   └── views/          # Arcade Views (Editor, Menu, Game)
│   ├── engine/             # Core Logic
│   │   ├── mechanics/      # Gameplay logic (Economy, Territory)
│   │   ├── mod_manager.py  # Dependency resolution
│   │   └── simulator.py    # Main Loop & System Graph
│   ├── server/             # Backend (State & IO)
│   │   ├── io/             # Data Loaders/Exporters
│   │   ├── session.py      # Game lifecycle host
│   │   └── state.py        # Polars DataFrame Store
│   └── shared/             # Code shared between Client/Server
│       ├── map/            # RegionAtlas (CV2 logic)
│       └── config.py       # Path management
├── tools/
│   └── mapgen.py           # Map compiler (SHP -> PNG/TSV)
└── window.py               # Entry point

```

## 🛠️ Tech Stack

* **Runtime:** Python 3.10+
* **Data Engine:** [Polars](https://pola.rs/) (Rust-backed DataFrames)
* **Rendering:** [Arcade](https://api.arcade.academy/) (OpenGL)
* **UI:** [ImGui Bundle](https://github.com/pthom/imgui_bundle)
* **Map Processing:** OpenCV, NumPy
* **Configuration:** RToml

## 🗺️ MVP Roadmap Status

Below is the current status of the Minimum Viable Product (MVP) features:

* [x] **Set up Saves** (Implemented via `SaveManager`: Atomic, Parquet-based)
* [ ] **Set up basic AI**
* [x] **Set up basic Player Management** (Session & NetworkClient handshaking implemented)
* [ ] **Stability** & **Expected Stability**
* [ ] **Population**, **Aging**, & **Growth**
* [ ] **Army (Personnel)**
* [x] **Region Conquest** (Implemented via `territory.py` & `ActionSetRegionOwner`)
* [x] **Region Annexation** (Supported by the `regions` dataframe owner column)

## 🧰 Tools: Map Generator

Included in `tools/mapgen.py` is a powerful map compiler designed for modders:

* **SHP to Game Data:** Converts GIS Shapefiles into game-ready `regions.png` and `regions.tsv`.
* **Micro-Nation Merging:** Automatically fuses tiny administrative divisions (e.g., Liechtenstein, Vatican) into clickable regions.
* **Smart Rescue:** Uses a spiral search algorithm to ensure small islands are not overwritten during rasterization.
* **Real Area Calculation:** Calculates `area_km2` using Cylindrical Equal Area projection for accurate gameplay stats.

## 🚀 Getting Started

1. **Install Dependencies:**
```bash
pip install arcade polars imgui-bundle opencv-python rtoml numpy rasterio geopandas

```


2. **Generate Map (Optional):**
If you have raw shapefiles, run the generator:
```bash
python tools/mapgen.py

```


3. **Run Engine:**
```bash
python -m src.client.window

```