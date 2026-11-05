# OpenPower Speckit Catalog

This catalog maps the implemented OpenPower codebase to its feature specifications. The
feature specifications describe observable behavior and contracts; their plans, data
models, contracts, quickstarts, and task lists hold the detailed design and acceptance
evidence.

## Coverage Map

| Code area | Specification |
| --- | --- |
| Process isolation, IPC snapshots, and session lifecycle | [001 — Multi-process IPC](001-ipc-multi-process-architecture/spec.md) |
| Geographic unit movement and route geometry | [002 — Geo military movement](002-geo-military-movement-system/spec.md) |
| Unit map rendering, flag atlas, clustering, and move selection | [003 — Unit batch renderer](003-unit-batch-renderer-atlas/spec.md) |
| Resource demand, trade, stockpiles, and national budgets | [004 — Economy and trade](004-internal-economy-budget-trade/spec.md) |
| Reusable AI scoring and policy action resolution | [005 — Polars AI orchestration](005-polars-ai-orchestration/spec.md) |
| Simulation time and population progression | [006 — Demographics and time](006-demographics-time-simulation/spec.md) |
| Treaty overlays and diplomatic map state | [007 — Treaties and alliances map overlay](007-treaties-alliances-map-overlay/spec.md) |
| Module discovery, registration, schemas, and system scheduling | [008 — Mod loader and ECS runner](008-dynamic-mod-loader-ecs-runner/spec.md) |
| Client navigation, loading, session startup, and audio | [009 — Client view and navigation](009-client-view-state-controller-ui/spec.md) |
| In-game inspector and dashboard panels | [010 — ImGui dashboard and inspectors](010-imgui-dashboard-inspector-panels/spec.md) |
| Map assets, indexes, shaders, and picking | [011 — Map rendering pipeline](011-map-rendering-pipeline-shaders/spec.md) |
| Save/load, migrations, and static world ingestion | [012 — State persistence and save I/O](012-state-persistence-save-io/spec.md) |
| Tactical readiness, orders, combat, and occupation | [101 — Tactical combat resolution](101-tactical-combat-resolution/spec.md) |
| Remote network multiplayer | [102 — Headless server multiplayer](102-headless-server-multiplayer/spec.md) — future capability; no network multiplayer implementation is present |
| Diplomacy and treaty lifecycle | [103 — Advanced diplomacy](103-advanced-diplomacy/spec.md) |
| Layered mod data and merge behavior | [104 — Mod data chaining](104-mod-data-chaining/spec.md) |
| Recognition, identity, and economic access | [105 — Recognition and economic access](105-un-recognition-economic-access/spec.md) |
| Battle markers, globe presentation, and visual states | [106 — Tactical battle visualization](106-tactical-battle-visualization/spec.md) |
| Migration and border mobility | [107 — Migration and border mobility](107-migration-and-border-mobility/spec.md) |
| Elections, parties, laws, and regime changes | [108 — Political lifecycle](108-political-lifecycle-and-regime-change/spec.md) |
| Covert missions, cells, and counterintelligence | [109 — Covert operations](109-covert-operations-and-counterintelligence/spec.md) |
| Strategic weapons and missile defense | [110 — Strategic warfare](110-strategic-warfare-and-missile-defense/spec.md) |
| Regional infrastructure and telecommunications | [111 — Infrastructure and telecom](111-regional-infrastructure-and-telecom/spec.md) |
| Economic health, debt, and default | [112 — Economic health and debt](112-economic-health-and-debt-failure/spec.md) |
| Military capabilities, research, and training | [113 — Military capability and training](113-military-capability-matrix-and-training/spec.md) |
| Unit production, deployment, and foreign orders | [114 — Production and deployment](114-production-deployment-and-foreign-orders/spec.md) |
| Battle posture and strategy | [115 — Battle strategy](115-battle-strategy-and-force-posture/spec.md) |
| Campaign selection, objectives, and advisor | [116 — Campaign scenarios and advisor](116-campaign-scenarios-objectives-and-advisor/spec.md) |
| Domain-event history, journals, and analytics | [117 — History and analytics](117-history-and-analytics/spec.md) |
| Random events and player controls | [118 — Random event impact and controls](118-random-event-impact-and-controls/spec.md) |
| Deterministic headless simulation runs and comparisons | [119 — Headless simulation runner](119-headless-simulation-runner/spec.md) |
| Module scaffolding and runtime validation commands | [120 — Mod authoring CLI](120-mod-authoring-cli/spec.md) |
| UI surface journeys, screenshot artifacts, and live smoke checks | [121 — UI journey test harness](121-ui-journey-test-harness/spec.md) |

## Speckit Artifact Conventions

Each in-scope feature has a `spec.md`, `plan.md`, `research.md`, `data-model.md`,
`quickstart.md`, and `tasks.md`. Feature-specific interface details live in
`contracts/`; requirement-quality checklists live in `checklists/`; measured performance
evidence lives in `performance-log.md` when the feature has a performance gate.

The early specifications 003–006, 008–009, and 011–012 now include explicit `FR-###`
requirements and a requirement-to-task table. Their existing technical details and
acceptance history remain in place.

## Scope Boundaries

The current implementation scope is defined by [implementation-scope.md](implementation-scope.md).
It excludes network multiplayer in feature 102 and editor-only acceptance embedded in
features 001, 009, 010, and 011. Gameplay and shared-client requirements in those feature
directories remain in scope. Existing editor code remains documented where useful and
is not removed by this scope boundary.

The source tree also has application-level rules in [the constitution](../.specify/memory/constitution.md),
runtime guidance in [Architecture](../docs/ARCHITECTURE.md), and module-author guidance in
[Modding API](../docs/MODDING.md). Those documents explain cross-feature conventions;
the numbered feature specifications remain the source of feature requirements.
