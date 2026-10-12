# Feature Specification: Advanced Diplomacy & Coalition Systems

## User Scenarios & Testing

### Primary User Story
As a national leader player, I want access to advanced diplomatic mechanisms—including peace negotiation packaging, bilateral asset offers, dynamic coalition building, and war exhaustion tracking—so that wars can be settled strategically and international power balances can be managed through diplomacy.

### Acceptance Scenarios
1. **Negotiating Peace Treaties**: **Given** warring nations with established war scores, **When** a player constructs a peace offer specifying reparations or territorial transfers, **Then** the recipient nation evaluates the proposal based on war exhaustion, relative strength, and strategic value before accepting or rejecting.
2. **Coalition Formation**: **Given** an expansionist country rapidly conquering neighboring regions, **When** their aggressive expansion threat score exceeds regional thresholds, **Then** threatened neighboring nations form a mutual defensive coalition to deter further aggression.
3. **War Exhaustion Impact**: **Given** an ongoing prolonged war, **When** casualties, economic blockades, and duration increase a nation's war exhaustion score, **Then** internal stability declines and public demand for peace imposes penalties on military efficiency.
4. **Bilateral Asset Offer**: **Given** two countries are not at war, **When** the player proposes cash, territory, or researched technology with a bounded deadline, **Then** the recipient can accept, reject, or counter, and the proposer can withdraw. Acceptance revalidates both sides and transfers the entire package atomically. An AI recipient uses the same asset validity rules and a deterministic exchange-value threshold.

### Edge Cases
- Multi-party peace negotiations involving alliance leaders and independent alliance members.
- Dynamic coalition dissolution when the primary threat collapses or cedes all conquered territories.
- AI leaders with opposing personality archetypes evaluating identical peace terms.

## Functional Requirements

- **FR-001**: Structured Peace Packaging: The diplomatic framework MUST support packaging multi-item peace treaties including war reparations, territory cessions, treaty annulments, and demilitarization.
- **FR-002**: Aggressive Expansion & Coalitions: The engine MUST compute regional threat scores from offensive military actions and trigger dynamic defensive coalition pacts among non-aligned states.
- **FR-003**: War Exhaustion Indexing: The simulation MUST calculate dynamic war exhaustion for all belligerents based on battle casualties, occupied provinces, blockade percentage, and conflict duration.
- **FR-004**: Multi-Factor AI Diplomacy: AI nations MUST evaluate diplomatic proposals against comprehensive utility functions incorporating economic sustainability, military balance, alliance obligations, and war exhaustion.
- **FR-005**: Diplomatic Telemetry & Map Overlays: Diplomatic statuses, coalition memberships, and war exhaustion levels MUST emit IPC events to update map color overlays and UI panels.
- **FR-006**: Bilateral Offer Lifecycle: The system MUST persist country-to-country offers of cash, owned regions, and researched technology in `diplomatic_trade_deals`. A valid proposal expires after 1–365 game days (default 30); the recipient may accept, reject, or counter, and the proposing country may withdraw. A counteroffer MUST link to the offer it replaces.
- **FR-007**: Bilateral Validation: The system MUST require authority over the acting country, existing participant countries, and non-belligerent participants. Cash MUST be available; offered regions MUST be owned, unoccupied, and leave the seller at least one region; technology MUST equal the seller's current research level and improve the recipient's level.
- **FR-008**: Atomic Settlement: On acceptance, the system MUST revalidate both packages immediately before settlement and apply cash, region ownership, capital fallback, and technology changes as one simulation outcome. A failed validation MUST not partially transfer any asset. The seller retains its technology level.
- **FR-009**: Deterministic Trade Evaluation: An AI recipient MUST accept a valid offer when value received is at least 90% of value requested. When below threshold it MAY construct a valid deterministic counteroffer from available requested assets; otherwise it rejects with a reason.
- **FR-010**: Trade Boundaries: Bilateral offers MUST NOT substitute for peace deals between belligerents or for resource imports/exports in the global market. This feature does not add network or multiplayer trade.

## Key Entities & Data Model

- **DiplomaticDeal**: Represents structured proposals containing offered and requested concessions, target nation IDs, status (pending/accepted/rejected), and expiration timestamps.
- **CoalitionPact**: Tracks coalition leader, member country IDs, primary target country ID, and mutual defense commitments.
- **WarExhaustionState**: Holds current war exhaustion index, accumulation rate, stability penalty, and peace desire factors for a country.
- **BilateralTradeDeal**: A pending or resolved proposal with source/target country, offered/requested assets, expiry, response, status/reason, and reciprocal counteroffer links.

## Scope Boundaries

Bilateral offers transfer cash, regions, and researched technology in the single-player simulation. They do not move resource-market commodities, settle wars, or implement multiplayer transport. Regional and technology values are deterministic AI heuristics rather than externally calibrated market valuations.

## Success Criteria

- **SC-001**: Instant AI Evaluation: AI evaluation of multi-clause diplomatic proposals occurs within a single simulation tick without stutter.
- **SC-002**: Dynamic Balance of Power: 100% of unprovoked rapid territorial annexations trigger appropriate counter-coalitions among vulnerable neighbors.
- **SC-003**: Clear Diplomatic Feedback: Diplomatic map modes and treaty panels update within 1 simulation tick of deal ratification.
- **SC-004**: 100% of accepted trade packages either transfer every validated asset or leave all country, region, government-capital, and research state unchanged.
- **SC-005**: Expiry, rejection, counteroffer, and withdrawal each resolve the pending offer once, retain a reason, and preserve its counteroffer link where applicable.
- **SC-006**: Repeating the same AI evaluation from identical state yields the same accept/reject/counter decision; acceptance follows the 90% value threshold.

## Assumptions & Dependencies

- **Assumption**: Existing treaty files (`countries_treaties.toml`, `countries_wars.toml`) provide foundational diplomacy data structure.
- **Dependency**: Polars AI orchestration framework (`src/core/ai_framework.py`) evaluates utility functions.
