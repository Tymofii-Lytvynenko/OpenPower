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
10. **Allocate a prioritized queue**: **Given** production capacity is insufficient for all queued work, **When** capacity is applied, **Then** earlier priority orders receive capacity first, the final eligible order may receive a partial allocation, and lower-priority orders wait until capacity becomes available.
11. **Deploy completed forces**: **Given** a production order finishes, **When** the unit is placed in the deployment queue and assigned a valid destination, **Then** it may be split into groups, remains absent from the active map while in transit, and becomes available at its destination on arrival.
12. **Price and cancel a foreign order**: **Given** the buyer and seller satisfy treaty eligibility and the seller accepts foreign orders, **When** a contract is created or cancelled, **Then** the default price and cancellation costs are shown and the cancelling party bears the documented production costs.
13. **Buy a used unit**: **Given** a seller lists an eligible existing unit, **When** an eligible buyer purchases it, **Then** the default price is based on 75% of its original production cost, embargoed buyers are excluded, and the seller may withdraw an unpurchased listing.

### Edge Cases

- Production capacity falls below queued demand; orders progress proportionally or pause according to the configured allocation rule.
- A high-priority order is inserted while another order is in transit; completed production is not rolled back and transit ownership remains explicit.
- A country loses the region, base, port, or route required for deployment; the order enters a visible blocked state.
- A foreign seller loses the design, funds, alliance, or legal permission before delivery; the order is cancelled or renegotiated according to its contract.
- A market listing expires, is cancelled, or is purchased twice; only one valid transaction can transfer ownership.
- A unit is destroyed or damaged while in transit; the loss is recorded and no duplicate unit is delivered.
- A legacy production order lacks capacity or route fields; it uses documented defaults and preserves completed progress.
- A country has queued work but no production capacity; no progress is fabricated and orders remain queued with a visible reason.
- A foreign-order seller has not enabled acceptance, or no eligible treaty or scenario permission exists; the request is rejected before funds or inventory change.
- A buyer is under a weapons embargo; used-unit listings cannot be purchased by that buyer.

## Functional Requirements

- **FR-001**: Each country MUST have a production capacity derived at the defined economic boundary from national economic output, economic health, and a scenario-configurable coefficient. The default formula MUST be `national output × economic health × production coefficient`.
- **FR-002**: Production orders MUST contain design, quantity, priority, assigned capacity, progress, remaining work, cost, owner, and lifecycle status.
- **FR-003**: The queue MUST support priority allocation, preemption, pause, resume, cancellation, and partial completion without losing completed work. Its default policy MUST allocate capacity sequentially by priority: each earlier order receives its full remaining demand when possible, the first order that cannot be fully served receives the remaining partial capacity, and subsequent orders wait. Scenario data MAY select another policy.
- **FR-004**: The player MUST see assigned capacity, progress, expected completion, funding requirement, blocking reason, and the effect of priority changes for every order.
- **FR-005**: A completed order MUST create one deployment-queued unit only once and MUST preserve the design, owner, training state, initial readiness, and production provenance. Its readiness transition MUST follow the existing readiness contract.
- **FR-006**: Deployment MUST require a valid domain-specific location and MUST support movement from the production or capital origin through a visible transit state.
- **FR-007**: Transit MUST calculate a deterministic route or route failure from distance, infrastructure, territorial control, diplomatic access, domain, and current war state.
- **FR-008**: Land and air units MUST deploy only to valid controlled territory or authorized bases. Naval units MUST use valid ports, sea zones, or international waters according to their design and scenario rules.
- **FR-009**: A foreign order MUST record buyer, seller, design, quantity, price, payment schedule, ownership timing, route, delivery date, deployment permissions, and cancellation rules.
- **FR-010**: Foreign orders MUST require an eligible alliance, weapons-trade treaty, or scenario permission; seller-side foreign-order acceptance MUST be enabled; and the specific order MUST be accepted. A buyer MUST NOT create a unit by unilateral request.
- **FR-011**: The existing used-unit market MUST share ownership, payment, listing, cancellation, and delivery rules with foreign orders and MUST NOT create a second inventory or transfer path.
- **FR-012**: Production and delivery MUST consume configured funds, resources, capacity, and maintenance obligations through existing economy, budget, resource, and military contracts.
- **FR-013**: AI-controlled countries MUST use the same queue, priority, deployment, transit, foreign-order, and market rules as human-controlled countries.
- **FR-014**: Every order, pause, reprioritization, cancellation, delivery, route block, transfer, and market transaction MUST publish a readable status and reason.
- **FR-015**: Identical production state, economic inputs, time, and ordered actions MUST produce identical allocation, completion, route, delivery, and ownership results.
- **FR-016**: Production queues, partial progress, deployment state, transit, foreign orders, listings, payments, and ownership transfers MUST survive save/load, snapshot synchronization, and replay.
- **FR-017**: Processing MUST update only queues with capacity changes, due progress, route changes, or order events when unrelated production state is unchanged.
- **FR-018**: Production capacity MUST use the default formula in FR-001 unless overridden by scenario data. The coefficient MUST be inspectable in the scenario configuration and MUST NOT be duplicated as a separate economic-health system.
- **FR-019**: A completed unit MUST enter a deployment list, and the owner MUST be able to split an order's units into valid groups before dispatch. A unit MUST have no active map presence or combat availability during transit and MUST become available for orders only after valid arrival; its readiness state MUST follow the existing readiness contract.
- **FR-020**: Deployment transit MUST begin from the configured capital or production origin and use the route, access, and domain rules in the military movement specification. Naval deployment to international waters MUST use its configured destination rules.
- **FR-021**: Foreign-order eligibility MUST expose the seller's standing acceptance state as well as per-order acceptance. The default price MUST be 125% of the equivalent new-production cost; scenarios MAY override the multiplier. A cancellation MUST retain the cancelling party's already-incurred production costs and apply the configured slight relationship penalty.
- **FR-022**: A seller MUST be able to list and withdraw an eligible used unit until purchase commits. The default used-unit price MUST be 75% of original production cost. A country under a weapons embargo MUST NOT be an eligible buyer. A completed market transfer MUST use the same payment, deployment, transit, ownership, and readiness pipeline as other foreign transfers.
- **FR-023**: Foreign designs MUST be visible only to countries eligible to order them. Eligible access MUST NOT transfer ownership of the seller's research or design records unless scenario data explicitly permits it.

## Key Entities & Data Model

- **Production Capacity Profile**: Country-level available capacity, economic factor, maintenance load, and allocation policy.
- **Production Order**: A prioritized request for one design and quantity with cost, progress, assigned capacity, and status.
- **Deployment Order**: A completed-unit placement request with domain, location, origin, route, transit, and arrival state.
- **Foreign Unit Order**: A seller-accepted contract for unit delivery between countries with payment, ownership, route, and permissions.
- **Unit Market Listing**: A listed unit with seller, design, condition, price, expiry, buyer, and delivery lifecycle.
- **Transit Record**: A unit’s origin, route, access checks, progress, arrival, interruption, and loss state.
- **Seller Acceptance Profile**: A seller's standing foreign-order acceptance state and any eligible buyer, design, or treaty restrictions.

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
- **SC-008**: Given the same national output, economic-health factor, and coefficient, production capacity equals their configured product at each economic boundary.
- **SC-009**: In queue-allocation tests, orders receive capacity in priority order, only the first partially served order receives residual capacity, and pause/resume preserves all completed work.
- **SC-010**: 100% of completed units remain outside the active map while in transit and become available only after valid arrival.
- **SC-011**: Foreign-order and used-market tests apply the configured default pricing, seller acceptance, embargo eligibility, cancellation costs, and single-transfer invariant.

## Assumptions & Dependencies

- **Assumption**: Existing production orders, unit designs, unit market, movement, treaties, and budget actions remain the starting contracts and are extended rather than duplicated.
- **Assumption**: Production capacity initially uses national output multiplied by economic health and a configurable coefficient; scenarios may override the coefficient or allocation policy.
- **Assumption**: Foreign-order price, cancellation penalty, and used-market price are scenario-configurable defaults of 125% of new production cost, a slight relation penalty plus incurred-cost responsibility for the cancelling party, and 75% of original production cost respectively.
- **Assumption**: Foreign orders transfer units through a contract and do not grant the buyer the seller’s research ownership unless scenario data explicitly permits it.
- **Dependency**: Existing economy, budget, resource, research, design, military movement, diplomacy, treaty, snapshot, and persistence contracts remain authoritative.
- **Dependency**: Transit access and naval deployment constraints use the military movement specification; unit availability on arrival uses the existing readiness specification.
