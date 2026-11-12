# Strict architecture linter: baseline audit

Audit date: 2026-11-12. The audited checkout was `0c5d9828`.

## Scope and method

The source audit parsed all 497 Python files under `src/` and `modules/`, including
imports guarded by `TYPE_CHECKING`. It found 12 `TYPE_CHECKING` branches, one
dynamic import site, and two module manifests. The `src/` and `modules/` roots are
namespace packages without root `__init__.py` files. The manifests declare no
dependencies for `base` and `energy_crisis -> base`; no Python cross-mod imports
or mod dependency cycles were present.

## Baseline violations

| Boundary | Current evidence | Recommended correction |
| --- | --- | --- |
| Client -> game modules | 17 imports across military and politics UI files use `modules.base` policy, catalogs, or systems. | Keep simulation policy in the mod; expose the required UI capabilities through a versioned, data/API-only client presentation extension loaded at the application boundary. |
| Client -> Engine | `src/client/ui/testing/fixtures.py` imported `ModManager`; this was test support stored under the production client package. | Move test tooling out of the Client package and update its test imports. |
| Engine -> Server | `src/engine/mod_manager.py` imports `CORE_SAVE_MIGRATIONS` from `src.server.io.migrations.py`. | Move the engine-owned default save migration to `src/core` and retain the existing server module only as a compatibility re-export if needed. |
| Server -> game module | `src/server/state_migrations.py` imports `BASE_TABLE_SCHEMAS` from `modules.base.schema`. | Supply the already-composed `WorldSchemaRegistry` to the migration instead of importing a concrete mod. |
| Engine <-> Server cycle | `src/server/session.py` imports Engine runtime classes while Engine imports Server migrations. | Removing the Engine -> Server edge breaks this cross-layer cycle without changing the session composition. |

The other current major-layer edges follow the intended direction: `core -> shared`,
`engine -> core/shared`, `server -> engine/core/shared`, `client -> core/shared`, and
`modules/base -> core/shared`. `main.py`, `src/cli.py`, `src/modding`, and
`src/simulation` are application or tooling composition points; production layers
must not acquire dependencies on those tools.

## Documentation conflicts

The requested `.specify/memory/constitution.md` path is absent; the active policy
is the root `CONSTITUTION.md`. It currently permits Engine -> Server and
Modules -> Engine interfaces, while `.agents/rules/engine.md` already forbids the
first edge and the requested contract forbids both. The Constitution also says
Shared may import only the standard library, while `.agents/rules/shared.md`
allows Polars and the current Shared sources additionally import NumPy,
`pycountry`, and `rtoml`. Removing those libraries would be a separate data/API
refactor, so the amendment should name the dependencies already used and keep
Shared an internal leaf layer.

## Other findings

- The only current computed import is the Engine `ModManager` loading
  `modules.<name>.registration`. This is a legitimate dynamic composition point;
  it should remain narrowly allowlisted and must not authorize other computed
  imports.
- The source already uses versioned module manifests. Static cross-mod imports
  can therefore be checked against the source mod's declared dependencies and
  that same manifest graph can be checked for cycles.
- The initial full Ruff rule set requested by the task reports 452 existing
  diagnostics: 308 import-order issues, 44 unused imports, 27 `zip` strictness
  issues, and 73 other diagnostics. Mass-fixing these would reformat unrelated
  code. Keep the broad legacy-style pass separate from blocking architecture and
  correctness rules, and enforce import ordering/Bugbear on new or changed files.

## Proposed implementation order

1. Add Import Linter contracts for layer direction, independent client/server
   hosts, protected Engine internals, and audited package roots.
2. Correct the two server/engine ownership edges and isolate the client
   presentation extension from simulation modules.
3. Add focused AST checks for manifest dependencies, dynamic imports, client
   state mutation, and package coverage.
4. Add positive and negative fixtures, a single cross-platform CLI, and a
   separate blocking Architecture workflow.

No exception is proposed for the baseline violations above. The only dynamic
loader allowances will be exact, named composition functions with regression
tests.

## Implemented result

The baseline had 20 direct cross-boundary import sites: 17 Client-to-module
imports, one Client-to-Engine test helper, one Engine-to-Server migration import,
and one Server-to-module schema import. Those edges also formed an Engine/Server
cycle. All were removed without a broad contract exception.

- The module migration defaults now live in `src/core/save_migrations.py`;
  `src/server/io/migrations.py` preserves the compatibility export.
- `src/server/state_migrations.py` receives the composed schema registry instead
  of importing a concrete module's schema.
- UI test helpers moved to `src/simulation/ui_testing/`, outside the production
  Client package.
- Client presentation behavior now arrives as a versioned
  `ClientPresentationContribution`, loaded by the app composition point. The
  Client no longer imports `modules.base`, and rendering receives a read-only
  `ClientGameStateView`; UI-only geography language state is kept separately.
- Treaty eligibility and covert-creation quotes are exposed through narrow
  client query services rather than returning simulation system objects.
  Client table mappings keep an isolated snapshot and clone Polars frames on
  reads so in-place DataFrame operations cannot mutate authoritative state.
- Import Linter currently analyzes 539 Python files and 1,958 dependencies. All
  11 configured contracts pass, including namespace roots, `TYPE_CHECKING`
  imports, layer direction, client/server independence, and protected Engine
  internals.
- The custom checker validates each module manifest, declared direct mod
  dependencies, dependency cycles, dynamic loader allowlists, client snapshot
  mutation rules, and source-root/package coverage. The baseline manifests had
  no cross-module Python imports or cycles; dedicated negative fixtures exercise
  missing declarations and cycles.
- Import Linter configuration is checked against an exact allowlist of root and
  required-contract options. Import exceptions, indirect-import allowances,
  package-scope weakening, and layer-container exclusions fail the architecture
  command, including when added to extra contracts.
- Dynamic loading is allowed only at `ModManager.load_runtime` for module
  registration and `load_client_presentation` for the presentation extension.
  Ruff's protected Engine API rule has only the two narrow audited importer
  exceptions needed for server session composition and simulation fixtures.
- Constitution 1.2.0 formally reconciles Shared's existing data dependencies
  and the layer contracts. `.agents/rules/` and `docs/ARCHITECTURE.md` now match
  the executable rules. Root `AGENTS.md` has contributor instructions above,
  and does not alter, the Repowise-managed section.
- The Architecture workflow runs on pull requests, pushes to `main`, and manual
  dispatch. It runs repository correctness/API Ruff checks, changed-file
  import-order/Bugbear checks, the single architecture CLI, and the negative /
  positive architecture fixture suite. The required status name is
  `Architecture / validate`.

## Deliberate limits and operations

The full repository still has legacy Ruff style diagnostics outside the files
changed for this architecture work. The recorded baseline full selection
reported 452 issues (308 import order, 44 unused imports, 27 zip strictness, and
73 other issues). To avoid mass formatting, blocking Ruff checks cover
correctness and banned APIs repository-wide, while `E7`, `I`, and `B` run on
changed Python files. The Import Linter and AST architecture checks remain
repository-wide and have no baseline exception.

The AST checker recognizes obvious literal/computed dynamic imports and permits
only the two exact production loader expressions above. Python can construct
imports through arbitrary runtime code, so static analysis cannot prove all
possible behavior. Runtime tests and review remain necessary for such behavior.

The repository workflow cannot set branch protection. In GitHub Settings, add
`Architecture / validate` to the required status checks for the protected main
branch.

## Verification results

Latest local checks on 2026-11-12:

- `uv run python -m tools.architecture_check`: passed; 539 files, 1,958
  dependencies, 11 contracts kept, and all custom AST and coverage checks
  passed.
- `uv run python -m ruff check src modules main.py --select
  E4,E9,F821,TID251,TID252`: passed.
- `uv run python -m ruff check --select E7,I,B <changed Python files>`:
  passed.
- The 32 architecture tests, including negative tests for all three Import
  Linter suppression options, passed in 13.51 seconds.
- The full repository suite passed after the follow-up fixes: 4,784 passed, 31
  skipped, 3 deselected, and 304 unittest subtests passed in 219.32 seconds.
  This run used a temporary junction to the checkout's ignored local `.codex`
  test assets because reference fixtures require them; the junction was removed
  after verification and is not part of this change.
- `ClientGameStateView` regression tests cover in-place `replace_column`,
  `insert_column`, `drop_in_place`, and `extend` mutations through returned
  Polars frames.
- The Base presentation extension now exports narrow treaty-eligibility and
  covert-creation quote services. Tests assert that client contributions do not
  expose `DiplomacySystem` or `CovertOperationsSystem` instances.

The workflow runs on PRs, pushes to `main`, and manual dispatch; pushing a
feature branch alone does not trigger it. Configure `Architecture / validate`
as a required status check after the workflow is available on the repository's
default branch.
