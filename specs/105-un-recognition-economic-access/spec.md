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
6. **Apply recognized economic access**: **Given** a country recognizes an annexed region, **When** the economic simulation evaluates cross-border activity involving that region, **Then** the recognized country may participate in the region's permitted economic flows.
7. **Block non-recognized economic access**: **Given** a country does not recognize an annexed region, **When** the economic simulation evaluates cross-border activity involving that region, **Then** the country receives no legal trade, financial, tax, or resource flow attributed to that region.
8. **Preserve domestic control**: **Given** an annexed region is controlled by its annexing country, **When** other countries reject or withhold recognition, **Then** military control, political ownership, and the annexer's domestic economic administration remain unchanged.
9. **Withdraw recognition after reversal**: **Given** an annexed region is no longer owned or controlled by the annexing country, **When** the simulation detects the reversal, **Then** active recognition statuses are withdrawn, the case is closed, and regional economic access is recalculated.
10. **Show the diplomatic state**: **Given** a player opens the UN Council or region details interface, **When** a case is pending or resolved, **Then** the player can see the region, claimant, former owner, deadline, aggregate result, and the selected country's recognition status.
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
- **FR-010**: Cross-border economic activity involving an annexed region MUST be permitted only when the participating foreign country has an active `recognized` status for the annexation. This restriction MUST cover regional resource trade, financial transfers, treaty-based economic benefits, taxation or revenue attribution, and other flows explicitly sourced from that region.
- **FR-011**: Economic calculations MUST retain the source region for regional output and flows. National aggregates MUST NOT be used to infer a region's output when no regional source record exists.
- **FR-012**: A non-recognizing country MUST NOT receive regional production, imports, exports, tax income, financial transfers, or treaty benefits attributed to the disputed region. Its unrelated domestic economy MUST continue to operate normally.
- **FR-013**: Recognition decisions MUST NOT change `regions.owner`, `regions.controller`, occupation state, military control, or map ownership. Recognition is a diplomatic and economic-access status, not a territorial transfer.
- **FR-014**: If the annexing country no longer owns or controls the region, all active recognition statuses for that annexation MUST be withdrawn, pending cases MUST be closed, and economic access MUST be recalculated.
- **FR-015**: The system MUST publish user-visible updates when a case opens, a vote changes, a case resolves, or recognition is withdrawn. Updates MUST identify the region and relevant countries.
- **FR-016**: The UN Council interface MUST show pending and resolved cases, voter deadline, vote totals, the user's current vote, and the recognition status for the selected country.
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
- **SC-004**: Within one state update after resolution, the council interface and region details show the final case status, vote totals, claimant, former owner, and selected-country recognition status.
- **SC-005**: In a controlled scenario, recognized countries can complete permitted economic interactions with an annexed region, while non-recognizing countries complete zero such interactions; unrelated economic activity remains unchanged.
- **SC-006**: Reversing ownership or control removes the region's recognized economic access for all affected countries on the next economic evaluation and does not alter unrelated regions.
- **SC-007**: Saving and loading a case at any point before or after resolution preserves all votes, deadlines, statuses, and the next economic-access result.
- **SC-008**: A player can determine the status of an annexation case and their country's recognition position from the available interfaces without inspecting raw state data.
- **SC-009**: With at least 1,000 active cases and 10,000 stored country-region recognition relationships, daily recognition processing completes within 250 milliseconds and does not cause visible interface stutter.

## Assumptions & Dependencies

- **Assumption**: The existing `countries.un_member` attribute is the authoritative and currently static UN membership source. Dynamic admission, suspension, or expulsion is outside this feature.
- **Assumption**: The initial council uses a strict majority of the eligible roster, has no permanent-member veto, and uses a thirty-game-day voting window. These rules are configurable for a later council-rules feature.
- **Assumption**: Recognition is bilateral. A passed council case records recognition for supporting states but does not force dissenting states to recognize the annexation.
- **Assumption**: The annexing country has domestic access because it controls and owns the region; foreign recognition governs cross-border economic access.
- **Assumption**: The simulation maintains one canonical national GDP and does not create a different GDP ledger for every foreign observer.
- **Dependency**: Completed annexation claims and ownership/control changes must remain available to the recognition process.
- **Dependency**: Full resource-level economic enforcement requires regional economic-output records with an explicit source region. Country-only production totals are insufficient for exact region-specific filtering.
- **Dependency**: Existing authoritative command, notification, snapshot, and save/load paths must carry recognition cases, votes, and statuses without allowing the client to mutate them directly.
- **Scope boundary**: This feature does not add permanent-member veto rules, dynamic UN membership, new sanctions systems, military intervention by the Council, or a new territorial ownership model.
