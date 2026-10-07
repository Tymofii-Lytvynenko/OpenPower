# UN Recognition and Regional Economic Access Research

## Existing Architecture Findings

- `RecognitionSystem` runs immediately after base diplomacy and consumes the existing `annexation_claims`, ownership/control, country, and action state.
- `countries.un_member` is the only membership authority. The case stores a sorted snapshot of eligible country IDs so subsequent votes use a stable roster.
- `ActionCastRecognitionVote` is validated by the authoritative system. Player authority is checked there; trusted AI decisions use the same roster, deadline, and vote replacement path.
- `recognition_cases`, `recognition_votes`, and `regional_recognition_status` are schema-registered `GameState` tables. Existing save, snapshot, and IPC paths serialize them with the rest of the state.
- `regional_production` is optional scenario data. The loader resolves region identifiers and validates finite, non-negative amounts; trade allocation rejects regional output above the corresponding national production total.
- `TreatyTradePolicy.allocate_with_regional_sources` retains `source_region_id`. `TradeSystem` evaluates recognition for each explicitly sourced bilateral allocation before applying it to national market outcomes.
- Diplomacy and region views consume read-only presenter projections; they do not mutate simulation tables.

## Decisions and Clarifications

### What counts as a completed annexation

The trigger is an existing annexation claim whose status is `annexed`, and whose region currently resolves to the claimant as both owner and controller. This avoids opening a case for a stale/invalid claim. A direct territory mutation that does not create or complete an annexation claim is not the feature's completion signal; this follows the spec's `Annexation Claim` entity and keeps recognition tied to the diplomatic lifecycle.

### Voting and recognition

The electorate is captured at opening from valid UN-member country rows, with claimant and former owner excluded. Votes are one-per-case-and-country and can be replaced only before the deadline. A strict majority of the captured roster is required. AI votes use relations, active wars, and eligible economic treaty signals with stable ordering and no randomness. A passed case stores bilateral statuses for the full electorate; a rejected case grants none.

### Regional economic provenance

Regional output must come from an explicit `[regional_resources.<region>.<resource>]` scenario record. The market allocator may retain an unattributed remainder but must not infer its source by subtracting or apportioning national aggregates. When a flow has `source_region_id`, its foreign bilateral allocation is blocked unless the exporter owns and controls the region and the importer has active recognition. Domestic owner access is allowed only while owner and controller match.

The current economy has country-level aid/credit/budget records without a source-region field. Those records are not treated as region-attributed transfers. This is deliberate: inventing provenance from national totals would violate FR-011. If a future system creates a region-sourced transfer, tax, or treaty benefit, its record must carry the source region and pass the same access policy before it is applied. This does not change unrelated country-level finance or treaty behavior.

### Reversal and persistence

When owner or controller changes, the next recognition update closes pending/passed cases and timestamps withdrawal of recognized statuses. Regional access is then denied on the next economy evaluation. Typed registered tables provide deterministic save/load and snapshot continuation without a separate persistence implementation.

## Performance Gate: SC-009

The opt-in test `tests/test_recognition_performance.py` builds 1,000 pending cases with 10,000 existing votes and 10,000 recognition-status rows, then measures a new-day update. The required limit is 250 ms. Recorded controlled runs are 0.035 s, 0.052 s (focused suite), and 0.061 s (fresh standalone run), all passing. These are repeat measurements, not optimization iterations; no optimization change was needed.

The benchmark does not measure 1,000 cases resolving on the same deadline, a large annexation-claim revision, or worst-case regional-access checks across many regions per trade cycle. Track these as future workload risks and optimize only after a reproducible gate failure, with no more than three measured iterations per algorithm.
