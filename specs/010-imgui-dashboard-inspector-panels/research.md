# Research: ImGui Dashboard & Data Inspector Panels

## Existing implementation findings

- `BudgetPanel` already has draft sector ratios, custom draggable ratio bars, a save/apply action, and client-side clamping for sector allocations. `ActionUpdateBudget` and `BudgetSystem` already support `personal_income_tax_rate`, but the panel does not expose that field. The feature gap is therefore in the UI and action payload, not in a new server contract.
- `DataInspectorPanel` already implements literal case-insensitive search, stable nulls-last sorting, a cached Polars display frame, and `imgui.ListClipper`. Its test proves that only visible rows are drawn for a 10,000-row frame. This proves virtualization behavior, not the <4 ms wall-clock/render target.
- `ResourcesPanel` presents production, consumption, trade, and balance in tables but has no plot. It also catches broad exceptions in resource-ledger rendering/policy sync/market rendering; some failures are discarded and another is converted to a generic message. Validate required columns explicitly and show a useful diagnostic instead.
- `ImGuiService` owns the application ImGui context. The installed binding exposes ImPlot context create/current/destroy operations and `plot_bars` plus labeled axis ticks. A plot context must be selected together with its matching ImGui service before drawing and destroyed before its ImGui context.
- `PoliticsSystem` is already extended with active rights, economic, crisis, migration, event, and war-exhaustion behavior. The baseline equation uses the requested 0.05 drift but has a stale 0.1 comment, missing/null fallbacks are inconsistent, and the weekly boundary uses calendar day-of-month modulo 7. The engine's global `tick` is a simulation-step counter, so it must not be used as the weekly calendar.

## External API verification

Context7 documentation for `/pthom/imgui_bundle` and installed binding docstrings confirm:

```python
implot.create_context()  # after imgui.create_context()
implot.set_current_context(plot_context)
implot.begin_plot(title)
implot.setup_axis_ticks(axis, values, labels=labels)
implot.plot_bars(label, values, bar_size=0.67)
implot.end_plot()
implot.destroy_context(plot_context)  # before imgui.destroy_context()
```

References: [ImGui Bundle plotting guide](https://github.com/pthom/imgui_bundle/blob/main/docs/book/addons/plotting.md), [Python API docs](https://context7.com/pthom/imgui_bundle).

## Chosen behavior

- Budget ratio controls include the personal income tax ratio and all sector ratios in one `ActionUpdateBudget` payload; every submitted value is finite and clamped to `[0, 1]`.
- Resource balance bars display the top eight resource rows already available in the market summary, with labeled resource names and import/export/net amounts. No new simulation calculation or trade semantics are introduced.
- Politics uses elapsed whole game days (`total_minutes // 1440`) to identify each seven-day boundary, gated by `EventNewDay`; this cadence is stable across month boundaries. The baseline target follows the exact requested weighted equation and fallback values. Existing political signals remain explicit modifiers after that baseline.
- Missing resource schema fields are shown to the player/developer with the missing field names. Unexpected exceptions are not swallowed.
- Performance results are recorded separately from correctness. Tuning may use no more than three measured iterations per algorithm; unresolved gates are explicitly deferred with results.
