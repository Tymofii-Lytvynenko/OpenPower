# Feature Specification: Production, Deployment, and Foreign Orders

## User Scenarios & Testing

### Primary User Story

As a military planner, I want production capacity, prioritized queues, deployment routes, transit, and foreign unit orders to behave predictably, so that building an army is a strategic logistics decision rather than an instant count increase.

### Acceptance Scenarios

1. **Allocate production capacity**: **Given** a country has a production capacity derived from its economic state, **When** the player queues multiple orders, **Then** capacity is allocated by priority and each order shows progress, remaining capacity, and expected completion.
2. **Pause and resume**: **Given** an order has partial progress, **When** the player pauses or reprioritizes it, **Then** completed progress is retained and future capacity follows the new allocation.
3. **Deliver a domestic unit**: **Given** a unit order completes, **When** the player selects a valid deployment region, **Then** the unit enters deployment or transit and becomes available only after the route and arrival conditions are satisfied.
4. **Transit from a capital**: **Given** a unit must travel from its production or capital origin to a deployment region, **When** the route is valid, **Then** transit time and reliability reflect distance, infrastructure, control, and current access.
5. **Place naval and air forces**: **Given** a unit has a domain-specific deployment rule, **When** the player chooses a location, **Then** land, air, and naval units are restricted to valid controlled territory, bases, ports, or international waters as appropriate.
6. **Request a foreign order**: **Given** an eligible seller and buyer have an alliance or weapons-trade relationship, **When** the buyer requests a unit order and the seller accepts, **Then** price, delivery, ownership, route, and deployment permissions are recorded.
7. **Reject an invalid foreign order**: **Given** the relationship, payment, design, route, or target deployment is invalid, **When** a foreign order is submitted, **Then** it is rejected without creating a unit or transferring funds.
8. **Use the unit market**: **Given** an owner lists an eligible unit, **When** another country buys it, **Then** the listing, payment, ownership, transit, and readiness state change in one auditable transaction.
9. **Persist the pipeline**: **Given** queues, partial production, transit, or foreign orders are active, **When** the game is saved and loaded, **Then** progress, priority, route, and ownership continue identically.

### Edge Cases

- Production capacity falls below queued demand; orders progress proportionally or pause according to the configured allocation rule.
- A high-priority order is inserted while another order is in transit; completed production is not rolled back and transit ownership remains explicit.
- A country loses the region, base, port, or route required for deployment; the order enters a visible blocked state.
- A foreign seller loses the design, funds, alliance, or legal permission before delivery; the order is cancelled or renegotiated according to its contract.
- A market listing expires, is cancelled, or is purchased twice; only one valid transaction can transfer ownership.
- A unit is destroyed or damaged while in transit; the loss is recorded and no duplicate unit is delivered.
- A legacy production order lacks capacity or route fields; it uses documented defaults and preserves completed progress.

## Functional Requirements

- **FR-001**: Each country MUST have a production capacity that is derived from configured national economic output and economic-health factors and is recalculated at the defined economic boundary.
- **FR-002**: Production orders MUST contain design, quantity, priority, assigned capacity, progress, remaining work, cost, owner, and lifecycle status.
- **FR-003**: The queue MUST support priority allocation, proportional or sequential capacity policy, preemption, pause, resume, cancellation, and partial completion without losing completed work.
- **FR-004**: The player MUST see assigned capacity, progress, expected completion, funding requirement, blocking reason, and the effect of priority changes for every order.
- **FR-005**: A completed order MUST create a deployment-ready unit only once and MUST preserve the design, owner, training state, readiness, and production provenance.
- **FR-006**: Deployment MUST require a valid domain-specific location and MUST support movement from the production or capital origin through a visible transit state.
- **FR-007**: Transit MUST calculate a deterministic route or route failure from distance, infrastructure, territorial control, diplomatic access, domain, and current war state.
- **FR-008**: Land and air units MUST deploy only to valid controlled territory or authorized bases. Naval units MUST use valid ports, sea zones, or international waters according to their design and scenario rules.
- **FR-009**: A foreign order MUST record buyer, seller, design, quantity, price, payment schedule, ownership timing, route, delivery date, deployment permissions, and cancellation rules.
- **FR-010**: Foreign orders MUST require an eligible alliance, weapons-trade, or scenario permission and explicit seller acceptance. A buyer MUST NOT create a unit by unilateral request.
- **FR-011**: The existing used-unit market MUST share ownership, payment, listing, cancellation, and delivery rules with foreign orders and MUST NOT create a second inventory or transfer path.
- **FR-012**: Production and delivery MUST consume configured funds, resources, capacity, and maintenance obligations through existing economy, budget, resource, and military contracts.
- **FR-013**: AI-controlled countries MUST use the same queue, priority, deployment, transit, foreign-order, and market rules as human-controlled countries.
- **FR-014**: Every order, pause, reprioritization, cancellation, delivery, route block, transfer, and market transaction MUST publish a readable status and reason.
- **FR-015**: Identical production state, economic inputs, time, and ordered actions MUST produce identical allocation, completion, route, delivery, and ownership results.
- **FR-016**: Production queues, partial progress, deployment state, transit, foreign orders, listings, payments, and ownership transfers MUST survive save/load, snapshot synchronization, and replay.
- **FR-017**: Processing MUST update only queues with capacity changes, due progress, route changes, or order events when unrelated production state is unchanged.

## Key Entities & Data Model

- **Production Capacity Profile**: Country-level available capacity, economic factor, maintenance load, and allocation policy.
- **Production Order**: A prioritized request for one design and quantity with cost, progress, assigned capacity, and status.
- **Deployment Order**: A completed-unit placement request with domain, location, origin, route, transit, and arrival state.
- **Foreign Unit Order**: A seller-accepted contract for unit delivery between countries with payment, ownership, route, and permissions.
- **Unit Market Listing**: A listed unit with seller, design, condition, price, expiry, buyer, and delivery lifecycle.
- **Transit Record**: A unit’s origin, route, access checks, progress, arrival, interruption, and loss state.

## Scope Boundaries

This feature completes production allocation, deployment, transit, and foreign ordering around existing production, design, unit-market, movement, diplomacy, and economy contracts. It does not replace research, unit capability, battle resolution, treaty rules, resource pricing, or territorial ownership.

## Success Criteria

- **SC-001**: 100% of queued orders show capacity allocation, progress, completion estimate, and blocking reason; invalid orders consume no funds or capacity.
- **SC-002**: Pausing, resuming, and reprioritizing an order preserves completed work and produces the documented allocation on the next update.
- **SC-003**: 100% of delivered units have a single production provenance, valid owner, valid location, and explicit transit history.
- **SC-004**: 100% of invalid foreign orders and duplicate market purchases create no duplicate unit or ownership transfer.
- **SC-005**: Repeated seeded runs and save/load reproduce identical queue progress, deliveries, payments, and ownership.
- **SC-006**: A player can determine when a queued unit will be completed and where it will arrive within 30 seconds.
- **SC-007**: Updating 50,000 orders and 100,000 transit records completes within 1 second in a controlled benchmark when only due records advance.

## Assumptions & Dependencies

- **Assumption**: Existing production orders, unit designs, unit market, movement, treaties, and budget actions remain the starting contracts and are extended rather than duplicated.
- **Assumption**: Production capacity initially uses configurable economic output multiplied by economic health; scenarios may override the factor.
- **Assumption**: Foreign orders transfer units through a contract and do not grant the buyer the seller’s research ownership unless scenario data explicitly permits it.
- **Dependency**: Existing economy, budget, resource, research, design, military movement, diplomacy, treaty, snapshot, and persistence contracts remain authoritative.
