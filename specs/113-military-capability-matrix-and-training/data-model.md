# Data Model: Military Capability Matrix and Training

## Unit role profile

The immutable role catalog is keyed by canonical role and contains a fixed deployment domain, baseline capability values, valid target categories, and vulnerabilities. Scenario/module data may add roles without modifying the simulation runner. Capability values remain bounded by the definitions in `capability_catalog.py`; missing values resolve to the documented neutral/not-applicable value rather than an inferred advantage.

## Unit design

The existing `unit_designs` table remains authoritative for country-owned design choices:

| Field group | Contract |
|---|---|
| Identity | Stable design ID, owning country, branch, class/role, display name, and domain |
| Design values | Quality, cost, maintenance, speed/firepower, and JSON-encoded variable capability values |
| Interactions | JSON-encoded valid targets and vulnerabilities |
| Availability | Research requirements and current research level |

Fixed role values come from the catalog. A design may only override documented variable characteristics; the existing research program system validates ownership, domain, role prerequisites, and funding/production constraints.

## Unit capability projection

The existing `unit_capability_projections` table is keyed by `unit_id` and contains owner, role, domain, bounded capabilities, valid target categories, vulnerabilities, training level, research level, and the last effective update time. It is derived from the unit, its design, its owner's research, and configured training bonuses. The battle resolver consumes it; it does not own or persist the source decisions.

## Training facility

Add the registered `unit_training_facilities` table as scenario/module-authored infrastructure:

| Field | Type | Meaning |
|---|---|---|
| `id` | Utf8, primary key | Stable facility identifier |
| `country_id` | Utf8 | Controlling country |
| `region_id` | Int32 | Training location |
| `supported_domains` | List[Utf8] | Eligible unit domains; `all` is an explicit wildcard |
| `capacity` | Int32 | Maximum simultaneous training orders |
| `instructor_count` | Int32 | Eligible training capacity source |
| `enabled` | Boolean | Whether the site currently accepts training |

A site with no remaining capacity, no instructor, an incompatible domain, or no valid region is ineligible. Training requires a site in the unit's current region, so the unit does not silently relocate while the training order removes it from active map presence. Among eligible local sites, selection is deterministic by stable facility ID. The order records the chosen site so subsequent ticks do not silently move the unit between facilities.

## Training order

The existing `unit_training_orders` table remains the durable lifecycle record and gains assigned facility/location identity while retaining its stable order ID, unit/country IDs, source/target level, progress, required duration, cost, status, return location, timestamps, and blocking reason. Status transitions are `active ↔ paused`, `active → completed`, `active/paused → cancelled`, and `active → blocked`. Pausing for unavailable capacity/instructors preserves accumulated progress and already-paid cost; explicit cancellation returns the unit to its recorded deployment location.

## Military intelligence finding and estimate view

The persisted `covert_findings` row remains the observation record: source country, target country, mission category, discovery/attribution authorization, confidence, discovery/expiry times, and JSON output. Military espionage output adds deterministic aggregate counts by canonical unit role alongside total/ready estimates; it contains no unit IDs or raw enemy design records. Readiness-start events may create `military_mobilization` findings only for foreign, active espionage coverage deployed in the target country. These findings contain the readiness transition, broad force domain, bounded confidence factors, and expiry, but neither unit nor cell identity; existing military-intelligence treaties may share them under the receiver's confidence cap.

The client presenter derives a read-only `ForeignForceEstimate` with target country, optional role-count ranges, total-count range, source country, source kind (owned observation or eligible ally), observed time, confidence, freshness, and status (`estimated`, `outdated`, or `unknown`). The best eligible source is selected by confidence × freshness, with stable source-country/observation-time tie breakers. Counts are displayed as ranges whose width grows as confidence falls; an active wartime opponent with no authorized current observation receives an explicit `unknown` view, never a zero-strength force. The view is derivable from persisted findings, treaties, and active war sides, so it requires no second authoritative estimate store.

## Persistence and synchronization

Training facilities, orders, unit lifecycle fields, designs, research tracks, capability projections, and espionage findings use registered Polars table schemas and stable keys. Save/load, IPC snapshot synchronization, and replay preserve those tables through the existing generic state mechanisms. The estimate view itself is recomputed from authorized persisted observations and current game time; recomputation must be deterministic and must not mutate state.
