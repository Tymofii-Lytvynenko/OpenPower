# Feature Specification: Political Lifecycle and Regime Change

## User Scenarios & Testing

### Primary User Story

As a national leader, I want governments, parties, laws, approval, elections, and regime stability to evolve over time, so that internal politics creates meaningful constraints and consequences for my strategy.

### Acceptance Scenarios

1. **Form a government**: **Given** a country has a government form and a ruling party, **When** the political state is opened, **Then** the player can see its election rules, law permissions, approval, stability, and corruption.
2. **Change a law**: **Given** the ruling government is allowed to change a law, **When** the player submits a valid law change, **Then** the law enters its configured transition and produces the appropriate approval, stability, budget, migration, or rights effects.
3. **Run an election**: **Given** an electoral government reaches its election date, **When** the election resolves, **Then** party support, turnout, eligibility, and current political conditions determine the winning government and the result is recorded.
4. **Use an election override**: **Given** a government can postpone, suppress, or accelerate an election under its configured rules, **When** the player selects the action, **Then** the system applies its cost and political consequences and records the next legal election date.
5. **Handle approval loss**: **Given** approval or stability falls below a configured threshold, **When** the political update runs, **Then** protests, strikes, opposition pressure, or government crisis can occur according to the country’s regime rules.
6. **Resolve regime change**: **Given** a coup, revolution, succession, or constitutional transition condition is met, **When** the event resolves, **Then** the government form, ruling authority, laws, approval, stability, and affected relations change as one auditable political outcome.
7. **Apply domestic effects**: **Given** a government changes its tax, labour, rights, or migration laws, **When** the next dependent systems update, **Then** the country’s budget, migration, economy, public approval, and military readiness use the active law state.
8. **Use AI politics**: **Given** a country is AI-controlled, **When** an election, law choice, or crisis becomes actionable, **Then** the AI follows the same legal rules, deadlines, costs, and outcome calculations as a human player.
9. **Persist the lifecycle**: **Given** a political transition is pending or resolved, **When** the game is saved and loaded, **Then** dates, votes, parties, laws, and political effects continue without divergence.
10. **Set language and religion policy**: **Given** the country has loaded identity profiles, **When** the player inspects or changes a language/religion group status, **Then** the interface shows shares and their source caveat, rejects changes to the aggregate `Other` group, records the authorized decision, and updates the declared rights/stability signals. Daily composition drift transfers only a bounded share to a recognized group and does not move population between regions.

### Edge Cases

- A country has no eligible opposition party; the election uses the configured fallback and does not create a null government.
- A law change is submitted after its deadline, during a government crisis, or without authority; it is rejected with a reason.
- Approval and stability cross several thresholds in one update; each threshold is resolved once in deterministic order.
- A government changes while a law transition is pending; the law follows its explicit carry-over or cancellation rule.
- A country has no election because its government form is non-electoral; an election action is unavailable rather than silently ignored.
- A coup attempt fails, is detected, or loses support; the country remains in the prior regime and receives the configured consequences.
- A legacy save contains seeded laws but no lifecycle metadata; the system derives a valid initial political state without changing existing ownership.
- A political effect would make approval, stability, or corruption leave its allowed range; values are clamped and the cause remains visible.
- A language or religion profile is missing, has unknown source year, or contains the aggregate `Other` row; unavailable profiles stay visibly absent, unknown provenance is disclosed, and the aggregate row cannot be assigned a separate legal status.

## Functional Requirements

- **FR-001**: Every country MUST have a canonical government state containing government form, ruling authority, election eligibility, next election date, approval, stability, and corruption.
- **FR-002**: Government forms MUST be data-driven and MUST define executive succession, election rules, party participation, law permissions, crisis thresholds, and available regime-change paths.
- **FR-003**: The political system MUST represent parties or political factions with support, ideology or policy positions, organization, eligibility, and ruling status.
- **FR-004**: Laws MUST have a current state, allowed values, transition duration, legal authority, and explicit effects. A law MUST NOT change merely because a UI control was opened.
- **FR-005**: Valid law changes MUST be scheduled through an authoritative political action, checked against government permissions, costs, cooldowns, and current crisis state.
- **FR-006**: Electoral governments MUST schedule elections at their configured interval, defaulting to four game years when no scenario override exists.
- **FR-007**: Election resolution MUST calculate eligible support, turnout, party results, coalition or succession outcome, and the resulting ruling authority using deterministic rules visible to the player.
- **FR-008**: The system MUST support configured election overrides such as postponement, acceleration, suspension, or succession. Each override MUST specify authority, duration, cost, and political consequences.
- **FR-009**: Approval, stability, and corruption MUST be separate values with bounded ranges and distinct causes. A change to one MUST NOT silently overwrite the others.
- **FR-010**: The system MUST evaluate protests, strikes, governmental paralysis, coup attempts, revolution, succession, and constitutional transition when their configured conditions are met.
- **FR-011**: A resolved regime change MUST apply its government, ruling authority, law, approval, stability, corruption, and relation effects atomically at one simulation boundary.
- **FR-012**: Active law effects MUST be published to dependent systems for taxation, labour, migration, public rights, economic behaviour, domestic stability, and military readiness without reimplementing those systems’ base calculations.
- **FR-013**: Political actions and AI decisions MUST obey country authority, action ordering, deadlines, costs, and cooldowns. The client MUST not mutate political state directly.
- **FR-014**: AI-controlled countries MUST use the same election, law, crisis, and regime-change rules as human-controlled countries and MUST expose the reason for major choices in the event history.
- **FR-015**: The system MUST publish readable messages for elections, law changes, approval crises, protests, coups, regime changes, and failed or rejected political actions.
- **FR-016**: Political state MUST survive save/load, snapshot synchronization, and replay with the same pending dates, transitions, and next valid outcomes.
- **FR-017**: The player MUST be able to inspect the current government, parties, active laws, next election, approval, stability, corruption, and recent political causes from one political overview.
- **FR-018**: Identical political state, time, and ordered actions MUST produce identical election results, crisis outcomes, and regime changes.
- **FR-019**: Identity Profiles: The political view MUST expose each loaded language and religion group, its normalized share, legal status, and source metadata. Unknown bundled source year MUST be represented as unknown, not assigned a current census year. The aggregate `Other` bucket is visible and non-editable.
- **FR-020**: Identity Policy Actions: An authorized player MUST be able to set a listed group's status to `official`, `legal`, `restricted`, or `illegal` through a shared action. Unauthorized, absent, unsupported, or aggregate-group changes MUST be rejected with a reason and no policy mutation. Restricting or banning a group MUST leave another nonzero group of that same dimension legally recognized.
- **FR-021**: Identity Composition: At an unpaused daily boundary, restricted and illegal groups MUST shift a bounded share to the largest recognized group in the same dimension at rates equivalent to 0.5% and 2% per game-year respectively. Shifts MUST preserve each profile total and MUST NOT change regional population, migration flows, or national population.
- **FR-022**: Identity Effects: For a country with identity groups, the system MUST calculate language and religion signals independently, average the available dimensions, and publish attributable bounded public-rights and stability effects for existing political consumers.
- **FR-023**: Identity Evidence: Policy changes and composition shifts MUST emit shared events and append attributable political history records with the prior/new status or share change and game minute.

## Key Entities & Data Model

- **Government State**: The current government form, ruling authority, succession status, election schedule, approval, stability, and corruption.
- **Political Party**: A party or faction with support, policy positions, organization, eligibility, and current governing role.
- **Law State**: A named domestic policy with current value, pending transition, legal authority, duration, and dependent effects.
- **Election**: A scheduled or overridden political contest with electorate, parties, turnout, results, winner, and resolution time.
- **Political Crisis**: A tracked protest, strike, paralysis, coup, revolution, succession, or constitutional transition with triggers, participants, status, and outcome.
- **Identity Group**: A country language or religion profile entry with normalized share, legal status, source metadata, and policy/composition timestamps.
- **Identity Policy Signal**: A per-country summary of language/religion group counts, recognized/restricted/illegal shares, bounded policy pressure, and update minute.

## Scope Boundaries

This feature activates the political lifecycle around the existing government and law records and adds legal identity policy for language/religion groups. Identity shares are game estimates rather than verified comparable census data. Identity composition changes do not simulate population movement or regional demographics. The feature does not replace existing economy, migration, military combat, or diplomatic relationship calculations and does not add multiplayer identity synchronization.

## Success Criteria

- **SC-001**: 100% of electoral governments receive a visible next election date and resolve an election at the configured interval unless a valid override is active.
- **SC-002**: 100% of invalid law, election, and regime-change actions are rejected without state mutation and include a reason visible to the player.
- **SC-003**: In controlled scenarios, each resolved law change updates every declared dependent signal within one simulation update and leaves unrelated signals unchanged.
- **SC-004**: Repeated runs with identical political inputs produce identical party results, crisis outcomes, and regime transitions.
- **SC-005**: A player can identify the current government, active laws, approval, stability, corruption, next election, and crisis cause within 30 seconds from the political overview.
- **SC-006**: Saving and loading during an election, law transition, or crisis preserves the next outcome and all deadlines.
- **SC-007**: Processing political state for 10,000 countries completes within 500 milliseconds in a controlled benchmark when no political state changed.
- **SC-008**: 100% of invalid identity-policy actions are rejected without changing the target group, aggregate signals, or political effects.
- **SC-009**: Repeated daily composition updates from identical group state/time produce identical shares and event/history records; each nonempty profile preserves its 100% total.
- **SC-010**: A player can see a group's source-year caveat, share, and legal status in the internal-laws view and can distinguish the aggregate `Other` row from editable groups.

## Assumptions & Dependencies

- **Assumption**: Government and law seed records are the starting data source and are extended with lifecycle fields rather than duplicated.
- **Assumption**: Electoral interval defaults to four game years, while individual government forms may override it.
- **Assumption**: Initial election rules use deterministic support and turnout formulas; detailed historical institutions remain scenario data.
- **Dependency**: Existing country stability, government, law, notification, action, snapshot, and save/load contracts remain authoritative.
- **Dependency**: Economy, migration, military readiness, and diplomacy consume declared political outputs through their existing system boundaries.
