# Feature Specification: Declarative Polars AI Orchestration Framework

## User Scenarios & Testing

### Primary User Story
As a single-player grand strategist, I want computer-controlled nations to evaluate economic survival and military ROI using declarative lazy evaluation graphs, so that AI nations make rational, data-driven decisions (raising taxes when bankruptcy approaches, building armies when GDP protection exceeds 5-year cost) without causing CPU tick slowdowns.

### Acceptance Scenarios
1. **Financial Survival Auditing (`audit_financial_survival`)**: **Given** an AI country with negative net annual balance (\(\text{Revenue} - \text{Expense} < 0\)), **When** `months_to_bankruptcy` falls below 12 months, **Then** `utility_survival_taxes` evaluates from `0.0` to `1.0`, triggering an `ActionUpdateBudget` to increase `personal_income_tax_rate` by 2%.
2. **Vectorized Military ROI Scoring (`calculate_military_roi`)**: **Given** an AI country evaluating troop recruitment, **When** the 5-year protected GDP benefit exceeds the 5-year unit total cost of ownership, **Then** `military_roi` evaluates positive and `ActionBuildUnit` is dispatched (provided `money_reserves > unit_5y_cost` and `annual_net_income > 0`).
3. **Single-Pass Materialization**: **Given** multiple functional scorers piped into a Polars LazyFrame, **When** `evaluate_and_act()` runs, **Then** Polars compiles all expressions into a single Rust backend execution sweep (`state_lf.collect()`), eliminating GIL bottlenecks.

### Edge Cases
- Positive cash flows (\(\text{annual\_net\_income} \ge 0\)): `months_to_bankruptcy` maps to `999.0`, resulting in `utility_survival_taxes = 0.0`.
- Diminishing marginal utility of military size: `MILITARY_DECAY_FACTOR` (\(0.85^{\text{military\_count}}\)) exponentially reduces protection yield, preventing wealthy nations from endlessly building armies until bankruptcy.
- Active cash deficit during army evaluation: `utility_build_army` drops to absolute `0.0` if `annual_net_income <= 0` or reserves are insufficient.

## Exact Mathematical Formulas & Scorers

### 1. Financial Survival Scorer (`audit_financial_survival`)
- **Annual Net Income**:
  \[ \text{NetIncome} = \text{Revenue}_{\text{total}} - \text{Expense}_{\text{total}} \]
- **Months to Bankruptcy Runway**:
  \[ \text{MonthsToBankruptcy} = \begin{cases} \left(\frac{\text{MoneyReserves}}{|\text{NetIncome}|}\right) \cdot 12 & \text{if } \text{NetIncome} < 0 \\ 999.0 & \text{otherwise} \end{cases} \]
- **Tax Hike Utility Trigger**:
  \[ \text{Utility}_{\text{taxes}} = \begin{cases} \text{clip}\left(1.0 - \frac{\text{MonthsToBankruptcy}}{12.0}, 0.0, 1.0\right) & \text{if } \text{MonthsToBankruptcy} < 12.0 \\ 0.0 & \text{otherwise} \end{cases} \]

### 2. Military ROI Scorer (`calculate_military_roi`)
- **5-Year Total Cost of Ownership (TCO)**:
  \[ \text{UnitCost}_{5\text{y}} = \$1,000,000 + (\$500,000 \cdot \text{HumanDev} \cdot 5.0) \]
- **5-Year Protected GDP Benefit**:
  \[ \text{UnitBenefit}_{5\text{y}} = (\text{GDP} \cdot 0.01 \cdot 0.85^{\text{MilitaryCount}}) \cdot \text{ThreatPerception} \]
- **Military Return on Investment (ROI)**:
  \[ \text{ROI}_{\text{military}} = \frac{\text{UnitBenefit}_{5\text{y}} - \text{UnitCost}_{5\text{y}}}{\text{UnitCost}_{5\text{y}}} \]
- **Build Army Utility Trigger**:
  \[ \text{Utility}_{\text{build\_army}} = \begin{cases} \text{clip}(\text{ROI}_{\text{military}}, 0.0, 1.0) & \text{if } \text{ROI} > 0 \land \text{Reserves} > \text{UnitCost}_{5\text{y}} \land \text{NetIncome} > 0 \\ 0.0 & \text{otherwise} \end{cases} \]

## Framework Architecture & Resolver Bindings

```
Polars LazyFrame (countries)
   │
   ├──> pipe(audit_financial_survival) ────> calculates utility_survival_taxes
   │
   └──> pipe(calculate_military_roi)   ────> calculates utility_build_army
   │
   ▼
single collect() pass (Rust backend)
   │
   ├──> utility_survival_taxes > 0.0 ──> ActionUpdateBudget (Tax + 0.02)
   │
   └──> utility_build_army > 0.0    ──> ActionBuildUnit (Army count + 1)
```

## Success Criteria

- **SC-001**: Rust Execution Performance: Evaluating financial and military utility across 200+ nations completes in under 2ms per evaluation pass.
- **SC-002**: Zero Bankruptcy Surprises: 100% of AI nations trigger proactive tax adjustments before reaching zero treasury reserves.
- **SC-003**: Scalable Decision Resolution: Adding new functional scorers requires zero changes to the underlying `DeclarativeAIFramework` execution loop.

## Assumptions & Dependencies

- **Assumption**: `DeclarativeAIFramework` (`src/engine/ai_framework.py`) handles registration and single-pass DataFrame collection.
- **Dependency**: `AISystem` in `modules/base/systems/world/ai_system.py` wires scorers and injects actions into `state.current_actions`.
