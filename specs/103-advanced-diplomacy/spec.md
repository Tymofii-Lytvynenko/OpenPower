# Feature Specification: Advanced Diplomacy & Coalition Systems

## User Scenarios & Testing

### Primary User Story
As a national leader player, I want access to advanced diplomatic mechanisms—including peace negotiation packaging, territory demands, dynamic coalition building, and war exhaustion tracking—so that wars can be settled strategically and international power balances can be managed through diplomacy.

### Acceptance Scenarios
1. **Negotiating Peace Treaties**: **Given** warring nations with established war scores, **When** a player constructs a peace offer specifying reparations or territorial transfers, **Then** the recipient nation evaluates the proposal based on war exhaustion, relative strength, and strategic value before accepting or rejecting.
2. **Coalition Formation**: **Given** an expansionist country rapidly conquering neighboring regions, **When** their aggressive expansion threat score exceeds regional thresholds, **Then** threatened neighboring nations form a mutual defensive coalition to deter further aggression.
3. **War Exhaustion Impact**: **Given** an ongoing prolonged war, **When** casualties, economic blockades, and duration increase a nation's war exhaustion score, **Then** internal stability declines and public demand for peace imposes penalties on military efficiency.

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

## Key Entities & Data Model

- **DiplomaticDeal**: Represents structured proposals containing offered and requested concessions, target nation IDs, status (pending/accepted/rejected), and expiration timestamps.
- **CoalitionPact**: Tracks coalition leader, member country IDs, primary target country ID, and mutual defense commitments.
- **WarExhaustionState**: Holds current war exhaustion index, accumulation rate, stability penalty, and peace desire factors for a country.

## Success Criteria

- **SC-001**: Instant AI Evaluation: AI evaluation of multi-clause diplomatic proposals occurs within a single simulation tick without stutter.
- **SC-002**: Dynamic Balance of Power: 100% of unprovoked rapid territorial annexations trigger appropriate counter-coalitions among vulnerable neighbors.
- **SC-003**: Clear Diplomatic Feedback: Diplomatic map modes and treaty panels update within 1 simulation tick of deal ratification.

## Assumptions & Dependencies

- **Assumption**: Existing treaty files (`countries_treaties.toml`, `countries_wars.toml`) provide foundational diplomacy data structure.
- **Dependency**: Polars AI orchestration framework (`src/engine/ai_framework.py`) evaluates utility functions.
