# Feature Specification: Dear ImGui Dashboard & Interactive Data Inspector Panels

## User Scenarios & Testing

### Primary User Story
As a grand strategy player, I want interactive ImGui dashboard panels (Budget, Economy, Demographics, Military, Politics, Resources, Data Inspector, Region Inspector) to control national policies and view macro metrics, political stability target drift, resource balances, and underlying Polars DataFrames in real-time.

### Acceptance Scenarios
1. **National Budget Panel**: **Given** the Budget Panel, **When** a player adjusts income tax sliders or sectoral expense ratios (`budget_health_ratio`, `budget_infra_ratio`, etc.), **Then** an `ActionUpdateBudget` is generated and dispatched to the server action queue.
2. **Political Stability Drift & Approval**: **Given** weekly political tick execution (`tick % 7 == 0`), **When** `PoliticsSystem` updates, **Then** target stability is calculated as \(\text{Target} = (0.7 \cdot \text{Approval} + 0.3 \cdot \text{HDI} - \text{Corruption}).\text{clip}(0, 100)\) and actual `gvt_stability` drifts 5% toward target weekly (\(\text{New} = \text{Old} + (\text{Target} - \text{Old}) \cdot 0.05\)).
3. **Resource & Economic Dashboards**: **Given** the Resources Panel, **When** inspecting resource balances, **Then** commodity consumption, production, imports, exports, and market balance are displayed using glassmorphism dark mode cards and ImPlot progress bars.
4. **Data Inspector Table Grid**: **Given** `data_insp_panel.py`, **When** a player selects a Polars table (`countries`, `regions`, `units`, `resource_ledger`), **Then** data is rendered in a virtualized ImGui table grid with column sorting and search filtering.

### Edge Cases
- Null or missing political metrics: Default fallbacks apply (`gvt_approval: 50.0`, `human_dev: 0.5`, `gvt_corruption: 0.1`, `gvt_stability: 50.0`).
- Dispatched budget slider updates: Allocations are clamped between `0.0` and `1.0` before sending to the simulation.

## Exact Mathematical Formulas & Political Equations

### Political Stability Target & Drift (`PoliticsSystem`)
- **Target Stability Equation**:
  \[ \text{TargetStability} = \text{clip}(0.7 \cdot \text{Approval} + 0.3 \cdot \text{HDI} - \text{Corruption}, 0, 100) \]
- **Weekly Stability Drift Equation** (\( \text{tick} \pmod 7 = 0 \)):
  \[ \text{Stability}_{\text{new}} = \text{int}\Big(\text{Stability}_{\text{old}} + 0.05 \cdot (\text{TargetStability} - \text{Stability}_{\text{old}})\Big) \]

## Panel Architecture Inventory

| Panel File | Primary UI Purpose | Polars Tables Displayed / Actions Issued |
| :--- | :--- | :--- |
| `budget_panel.py` | Tax sliders, sector expense allocations | `countries`, `resource_ledger` / `ActionUpdateBudget` |
| `economy_panel.py` | Macro GDP growth, internal tax collection | `countries`, `domestic_production` / `ActionSetTax` |
| `resources_panel.py` | Resource production, demand & trade ledger | `resource_ledger`, `stockpiles`, `trade_network` |
| `military_panel.py` | Unit recruitment, strength & manpower pool | `units`, `countries` / `ActionBuildUnit`, `ActionMoveUnit` |
| `politics_panel.py` | Government approval, corruption & stability drift | `countries` |
| `demographics_panel.py` | Age distribution (pop_14, pop_15_64, pop_65), TFR | `regions`, `countries` |
| `region_inspector.py` | Region owner, controller, population, area | `regions` / `ActionSetRegionOwner`, `ActionOccupyRegion` |
| `data_insp_panel.py` | Universal Polars DataFrame table viewer | All active tables in `GameState.tables` |

## Success Criteria

- **SC-001**: Interactive Responsiveness: UI sliders drag cleanly at 60+ FPS without input lag or state stutter.
- **SC-002**: Inspection Performance: Data Inspector renders 10,000+ row DataFrames with virtualized scrolling under 4ms per frame.
- **SC-003**: Accurate Drift Modeling: Political stability drifts towards target at exact 5% rate per week.

## Assumptions & Dependencies

- **Assumption**: `imgui_bundle` provides Python bindings for ImGui and ImPlot.
- **Dependency**: IPC snapshot stream delivers updated `GameState.tables` to UI panels.
