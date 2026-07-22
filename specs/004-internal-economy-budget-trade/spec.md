# Feature Specification: Internal Economy, Budget & Trade Simulation Systems

## User Scenarios & Testing

### Primary User Story
As a national economic manager, I want an economic simulation featuring dynamic wealth anchoring, income elasticity of demand, propensity to consume, sectoral budget allocations, internal taxation, tourism foreign levies, and global trade clearing with physical decay physics, so that macroeconomic policies realistically impact national growth, treasury reserves, and public satisfaction.

### Acceptance Scenarios
1. **Dynamic Demand & Wealth Anchoring**: **Given** national GDP per capita and global average GDP per capita, **When** computing resource demand, **Then** Wealth Index \( \text{WI} = \frac{\text{GDP}_{\text{pc}}}{\text{GlobalAvg}} \) scales solvent population consumption using income elasticity multipliers.
2. **Propensity to Consume Pooling**: **Given** a nation's total GDP, **When** calculating consumption capacity, **Then** poorer nations spend up to 90% of GDP on consumption while wealthy nations spend ~55%, compressing raw demand to match real economic capacity.
3. **Global Market Clearing & Ratios**: **Given** global resource supplies and demands, **When** trade clearing executes, **Then** import ratio \(\text{imp\_ratio} = \min(1.0, \frac{\text{global\_supply}}{\text{global\_demand}})\) and export ratio \(\text{exp\_ratio} = \min(1.0, \frac{\text{global\_demand}}{\text{global\_supply}})\) determine actual trade volumes.
4. **Physical Resource Decay & Service Evaporation**: **Given** storable vs non-storable goods, **When** stockpiles update, **Then** non-storable services (decay rate 1.0) evaporate instantly and trigger harsh 50% capacity layoffs if unsold, while storable goods decay per year (e.g. steel 3%, vehicles 25%, minerals 2%) with soft penalties when warehouses exceed 50% of annual production.
5. **Fiscal Revenue & Budget Collection**: **Given** personal income tax rates and tourism service exports, **When** daily budget ticks execute, **Then** tax revenue \( \frac{\text{GDP} \cdot \text{HDI} \cdot \text{TaxRate}}{3.0} \) and a 20% tourism foreign levy are credited to `money_reserves`.

## Exact Mathematical Formulas & Constants

### 1. Macroeconomic Demand & Consumption
- **Global Average GDP per Capita Anchor**:
  \[ \text{GlobalAvg} = \max\left(100.0, \frac{\sum \text{GDP}_{\text{total}}}{\sum \text{Population}}\right) \]
- **Wealth Index (WI)**:
  \[ \text{WI} = \text{clip}\left(\frac{\text{GDP}_{\text{pc}}}{\text{GlobalAvg}}, 0.05, 10.0\right) \]
- **Propensity to Consume Pool**:
  \[ \text{ConsumptionPool} = \text{GDP}_{\text{total}} \cdot \left(0.50 + \frac{0.40}{1.0 + \text{WI}}\right) \]
- **Resource Raw Demand Formula**:
  \[ \text{Demand}_{\text{raw}} = \left( \text{Pop}_{\text{solvent}} \cdot \text{Base}_{\text{solvent}} \cdot \text{WI}^e + \text{Pop}_{\text{total}} \cdot \text{Base}_{\text{general}} \right) \cdot \text{Mult}_{\text{output}} + \sum (\text{DepRes} \cdot \text{Coeff}) \]
- **Normalization Compression Factor**:
  \[ \text{NormFactor} = \frac{\text{ConsumptionPool}}{\sum \text{Demand}_{\text{raw}}} \]

### 2. Trade Physics & Decay Rates (`TradeSystem.RESOURCE_PHYSICS`)

| Resource Category | Decay Rate | Storable? | Spoilage / Penalty Mechanics |
| :--- | :--- | :--- | :--- |
| **Services & Energy** (electricity, health, transport, financial, etc.) | `1.00` (100%/yr) | **No** | Evaporates instantly; unsold volume causes 50% immediate capacity layoff. |
| **Fast Depreciation Goods** (vehicles, commodities, appliances) | `0.20`–`0.25` | **Yes** | 20-25% annual loss due to aging/obsolescence. |
| **Pharmaceuticals** | `0.15` (15%/yr) | **Yes** | Expiration dates & shelf life decay. |
| **Food & Agro Goods** (cereals, meat, dairy, fruits) | `0.10`–`0.15` | **Yes** | Spoilage and agricultural loss. |
| **Materials & Minerals** (minerals 2%, steel 3%, precious stones 0%) | `0.00`–`0.08` | **Yes** | Slow oxidation/rust; warehouses >50% GDP incur soft penalties. |

### 3. State Budget Revenues & Expenses
- **Personal Income Tax Revenue**:
  \[ \text{Rev}_{\text{tax}} = \frac{\text{GDP} \cdot \text{HumanDev} \cdot \text{TaxRate}}{3.0} \]
- **Tourism Foreign Levy**:
  \[ \text{Rev}_{\text{tourism}} = 0.20 \cdot \sum \text{Exports}_{\text{tourism\_services}} \]
- **Military Unit Upkeep Cost**:
  \[ \text{Expense}_{\text{military}} = \text{MilitaryCount} \cdot 500,000 \cdot \text{HumanDev} \]
- **Debt Interest Expense**:
  \[ \text{Expense}_{\text{interest}} = 0.05 \cdot |\text{MoneyReserves}| \quad (\text{if } \text{MoneyReserves} < 0) \]

## Success Criteria

- **SC-001**: Economic Realism: Dynamic consumption pooling restricts low-GDP countries from buying luxury goods while maintaining realistic basic food demand.
- **SC-002**: Fiscal Balance: Budget system accurately computes daily financial balances with zero floating point drift.
- **SC-003**: Polars Execution Speed: Full economic update for all 200+ global nations runs under 5ms per simulation tick.

## Assumptions & Dependencies

- **Assumption**: `RESOURCE_MAPPING` in `src/shared/economy_meta.py` categorizes all 37 resource types into Raw Materials, Energy, Industrial Materials, Finished Goods, and Services.
- **Dependency**: `EventRealSecond` events from `base.time` trigger real-second heartbeats.
