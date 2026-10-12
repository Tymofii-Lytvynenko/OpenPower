# Feature Specification: UN Recognition and Regional Economic Access

## User Scenarios & Testing

### Primary User Story

As a national leader, I want every completed territorial annexation to pass through a UN recognition process, so that each country's diplomatic stance is explicit and economic relations respect whether that country accepts the annexation.

### Acceptance Scenarios

1. **Open a recognition case**: **Given** an annexation has completed for a region, **When** the simulation processes the completed annexation, **Then** exactly one UN recognition case is opened for that region and records the annexing country and former political owner.
2. **Use the existing membership roster**: **Given** the country database identifies UN members, **When** the case creates its eligible voter roster, **Then** only countries marked as UN members are eligible, and the annexing country and former owner cannot vote on their own case.
3. **Cast a vote**: **Given** an eligible country has an open case, **When** its authorized player or AI casts a vote, **Then** the country's pending vote is recorded and can be changed until the voting deadline without creating duplicate votes.
4. **Resolve a passed case**: **Given** the voting deadline has passed and a strict majority of eligible members voted for recognition, **When** the case resolves, **Then** the case is marked passed, every supporting voter receives a recognized status, and opposing, abstaining, or absent members retain a not-recognized status.
5. **Resolve a rejected case**: **Given** the voting deadline has passed without a strict majority for recognition, **When** the case resolves, **Then** the case is marked rejected and no country receives a new recognized status from that case.
6. **Apply recognized economic access**: **Given** a country recognizes an annexed region, **When** the economic simulation evaluates a flow explicitly sourced from that region, **Then** the recognized country may participate in permitted regional resource trade and any other source-tagged economic flow supported by the simulation.
7. **Block non-recognized economic access**: **Given** a country does not recognize an annexed region, **When** the economic simulation evaluates a flow explicitly sourced from that region, **Then** the country receives no regional trade or derived tax/revenue, transfer, or treaty benefit attributed to that region; country-level flows without regional provenance are not attributed to the region by inference.
8. **Preserve domestic control**: **Given** an annexed region is controlled by its annexing country, **When** other countries reject or withhold recognition, **Then** military control, political ownership, and the annexer's domestic economic administration remain unchanged.
9. **Withdraw recognition after reversal**: **Given** an annexed region is no longer owned or controlled by the annexing country, **When** the simulation detects the reversal, **Then** active recognition statuses are withdrawn, the case is closed, and regional economic access is recalculated.
10. **Show the diplomatic state**: **Given** a player opens the UN Council or region details interface, **When** a case is pending or resolved, **Then** the player can see the region, claimant, former owner, and vote totals; while the selected country is eligible and has not voted, the council shows the remaining voting time; after a vote is submitted, it shows the current vote and allows replacement until the deadline; after resolution it shows the final case result and, for an eligible voter, that country's recognition status.
11. **Persist the outcome**: **Given** a case contains votes or recognition decisions, **When** the game is saved and loaded, **Then** the case, votes, statuses, deadlines, and economic access produce the same subsequent result.

### Edge Cases

- An annexation claim is invalidated before the recognition case opens; no case is created.
- The same annexation status is observed on multiple simulation ticks; only one active case exists.
- A country is not a UN member, is missing from the country roster, or has an invalid membership value; it cannot vote or receive a council vote slot.
- The annexing country or former owner attempts to vote; the action is rejected without changing the case.
- A country submits multiple votes before the deadline; only its latest valid vote is used.
- A case reaches its deadline with no votes, a tie, or only abstentions; it is rejected.
- A region changes owner or controller while a case is pending; the case closes and pending votes no longer grant recognition.
- A recognized country loses recognition after a reversal; all affected economic flows stop on the next simulation evaluation.
- A region has no regional resource-output record; the system must not silently attribute national production to that region.
- A non-recognizing country has an existing treaty or trade relationship with the annexing country; the regional recognition restriction takes precedence for flows sourced from the disputed region.
- The player lacks authority over the country named in a vote action; the action is rejected.
- A legacy save does not contain recognition tables; it starts with no open cases and preserves existing territory and economy data.

## Functional Requirements

- **FR-001**: The recognition process MUST use the existing country-level UN membership information as the authoritative eligibility source; it MUST NOT create a competing membership roster for the initial release.
- **FR-002**: The system MUST open one recognition case for every completed annexation and MUST associate the case with the region, annexing country, former political owner, and originating annexation record.
- **FR-003**: The system MUST prevent duplicate active cases for the same region and completed annexation, including after save/load or repeated simulation ticks.
- **FR-004**: The case MUST capture an eligible voter roster when it opens. Only UN members may be included; the annexing country and former owner MUST be excluded from voting on that case.
- **FR-005**: Each eligible country MUST have at most one current vote per case. A country MAY replace its vote before the deadline, and a vote after the deadline MUST be rejected.
- **FR-006**: The case MUST expose a configurable voting deadline measured in game time. The initial default MUST be thirty game days after case opening.
- **FR-007**: A case MUST pass only when the number of recognition votes is greater than half of the eligible voter roster. A tie, insufficient support, no votes, or an expired case without a majority MUST reject the case. Abstentions and missing votes MUST NOT count as recognition votes.
- **FR-008**: Recognition MUST be recorded per country and region. A supporting country in a passed case receives `recognized`; an opposing, abstaining, or absent country receives `not_recognized`. A rejected case MUST NOT create new recognized statuses.
- **FR-009**: The annexing country MUST retain domestic economic access to a region it owns and controls, regardless of foreign recognition. This domestic access MUST NOT be represented as foreign recognition for other countries.
- **FR-010**: Cross-border economic flows explicitly sourced from an annexed region MUST be permitted only when the participating foreign country has an active `recognized` status for the annexation. The initial implementation MUST gate bilateral resource-trade allocations carrying that region as `source_region_id` and any tax or revenue derived from those allocations. Any financial transfer, treaty-based benefit, or other flow explicitly sourced from a region MUST use the same access policy before its value is applied.
- **FR-011**: Economic calculations MUST retain the source region for regional output and for any flow represented as region-sourced. National aggregates MUST NOT be used to infer a region's output or to invent regional provenance for country-level flows.
- **FR-012**: A non-recognizing country MUST NOT receive regional production, trade, or derived tax/revenue, financial transfers, or treaty benefits explicitly attributed to the disputed region. Country-level flows without source-region provenance MUST remain country-level and MUST NOT be apportioned to the disputed region; unrelated domestic and national economic activity MUST continue to operate normally.
- **FR-013**: Recognition decisions MUST NOT change `regions.owner`, `regions.controller`, occupation state, military control, or map ownership. Recognition is a diplomatic and economic-access status, not a territorial transfer.
- **FR-014**: If the annexing country no longer owns or controls the region, all active recognition statuses for that annexation MUST be withdrawn, pending cases MUST be closed, and economic access MUST be recalculated.
- **FR-015**: The system MUST publish user-visible updates when a case opens, a vote changes, a case resolves, or recognition is withdrawn. Updates MUST identify the region and relevant countries.
- **FR-016**: The UN Council interface MUST show pending and resolved cases and vote totals. For a pending case, it MUST show the remaining voting time to an eligible selected country that has not yet voted; after submission, it MUST show that country's current vote and allow replacement until the deadline. After resolution, it MUST show the selected country's recognition status when that country belonged to the captured eligible voter roster.
- **FR-017**: The region details interface MUST show the annexing country, former owner, case status, recognition count, and the selected country's recognition status when recognition data exists.
- **FR-018**: AI-controlled countries MUST use the same vote and recognition rules as human-controlled countries. AI decisions MUST consider at least diplomatic relations, active wars, alliances, and economic interests without bypassing authorization or the case deadline.
- **FR-019**: The recognition process MUST be deterministic: identical state, time, and ordered actions MUST produce identical cases, votes, statuses, and economic-access results.
- **FR-020**: The recognition state MUST survive save/load, snapshot synchronization, and replay without changing the next valid outcome.
- **FR-021**: Recognition processing MUST be incremental and must not rescan every country-region pair on every simulation tick when no annexation, vote, membership, or ownership state has changed.

## Key Entities & Data Model

- **UN Recognition Case**: A time-bounded council proceeding for one completed annexation. It records the region, claimant, former owner, eligible voter roster, deadline, aggregate vote result, and lifecycle status.
- **Recognition Vote**: The current decision of one eligible UN member for one case: support, oppose, or abstain, with its submission time and authority context.
- **Region Recognition Status**: The durable per-country relationship describing whether a country recognizes the annexing country's claim to a specific region, including the originating case and withdrawal state.
- **Regional Economic Access**: The derived permission that determines whether a country may participate in economic flows sourced from an annexed region. It is based on domestic ownership/control for the annexer and active recognition for foreign participants.
- **Annexation Claim**: The existing territorial record that identifies when an annexation completes and supplies the claimant, former owner, and region identity for case creation.
- **UN Membership Attribute**: The existing country data attribute indicating whether a country is eligible for council participation. No separate membership table is required for the initial release.

## Success Criteria

- **SC-001**: 100% of completed annexations produce exactly one active recognition case by the next simulation update, with no duplicate cases after repeated ticks or save/load.
- **SC-002**: 100% of council voter rosters contain only UN members and exclude the annexing country and former owner; no ineligible vote changes a case.
- **SC-003**: At the voting deadline, identical state and actions produce the same case result and per-country recognition statuses across repeated runs.
- **SC-004**: Within one state update after resolution, the council interface and region details show the final case status, vote totals, claimant, former owner, and the selected eligible voter's recognition status.
- **SC-005**: In a controlled scenario with explicit regional production, recognized countries can complete permitted bilateral resource-trade allocations sourced from an annexed region, while non-recognizing countries complete zero such allocations and receive no derived tax/revenue from them; flows without regional provenance are not attributed to or gated as if sourced from that region.
- **SC-006**: Reversing ownership or control removes the region's recognized economic access for all affected countries on the next economic evaluation and does not alter unrelated regions.
- **SC-007**: Saving and loading a case at any point before or after resolution preserves all votes, deadlines, statuses, and the next economic-access result.
- **SC-008**: A player can determine the status of an annexation case and, when their country was on the captured voter roster, its recognition position from the available interfaces without inspecting raw state data.
- **SC-009**: With at least 1,000 active cases and 10,000 stored country-region recognition relationships, daily recognition processing completes within 250 milliseconds and does not cause visible interface stutter.

## Assumptions & Dependencies

- **Assumption**: The existing `countries.un_member` attribute is the authoritative and currently static UN membership source. Dynamic admission, suspension, or expulsion is outside this feature.
- **Assumption**: The initial council uses a strict majority of the eligible roster, has no permanent-member veto, and uses a thirty-game-day voting window. These rules are configurable for a later council-rules feature.
- **Assumption**: Recognition is bilateral. A passed council case records recognition for supporting states but does not force dissenting states to recognize the annexation.
- **Assumption**: The annexing country has domestic access because it controls and owns the region; foreign recognition governs cross-border economic access.
- **Assumption**: The simulation maintains one canonical national GDP and does not create a different GDP ledger for every foreign observer.
- **Assumption**: Recognition-based economic restrictions apply to flows with explicit source-region provenance. Existing country-level aid, credit, budget, and treaty records without regional provenance remain country-level and are not inferred from national aggregates.
- **Dependency**: Completed annexation claims and ownership/control changes must remain available to the recognition process.
- **Dependency**: Full resource-level economic enforcement requires regional economic-output records with an explicit source region. Country-only production totals are insufficient for exact region-specific filtering.
- **Dependency**: Existing authoritative command, notification, snapshot, and save/load paths must carry recognition cases, votes, and statuses without allowing the client to mutate them directly.
- **Scope boundary**: This feature does not add permanent-member veto rules, dynamic UN membership, new sanctions systems, military intervention by the Council, region attribution for existing country-level economic records, or a new territorial ownership model.
