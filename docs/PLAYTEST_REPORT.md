# Real client playtest

Date: 2026-10-08. Windows, Arcade/OpenGL client and a separate authoritative simulation process. The client profiler was disabled; live UI inspection was enabled. No specification performance thresholds were used.

## Verified interactions

- Open Singleplayer, scroll to Ukraine, select it, and start the sandbox campaign.
- Open Economy and Budget; enter 35% personal income tax and apply it.
- Confirm `personal_income_tax_rate == 0.35` in the server snapshot received by the client.
- Open the speed controls, choose speed 5, and pause. The authoritative state confirms both changes.
- Open Military and Unit List; the screenshot shows `UKR-army-001`, its strength, location, and parked status.
- Advance the campaign into January 2 without reported simulation system errors.
- Return to the main menu and exit through the UI.
- Start the final client again and confirm the menu appears only after the first decoded world snapshot is available.

The previous longer run reached January 4 and exposed intermittent snapshot reception stalls. The final run exercises the revised transport and background decoding. Its last 240 frame intervals had a median of 23.5 ms, 95th percentile of 52.2 ms, and maximum of 119.9 ms, with several panels and screenshot inspection active. This is a short practical observation, not a long-session guarantee.

## Fixes

- Campaign setup now allows real world initialization to finish; loading failures stay visible and recoverable instead of terminating the client.
- Duplicate extension keys no longer multiply regions and infrastructure records during data joins.
- History sampling reads the required columns, indexes subjects by indicator, and skips unchanged observations until sampling is due.
- Infrastructure depreciation uses column expressions when there are no active projects or damage events requiring the mutable path.
- Server controls and acknowledgements are processed between catch-up steps.
- Snapshot decoding runs outside the render loop. Published snapshots retain their own mutable containers.
- Growing history tables send append tails; compaction falls back to full table replacement.
- Snapshot protocol version 3 prevents older decoders from silently ignoring append payloads.
- UI source path resolution is cached, automatic widget alias replacement is indexed, and screenshot/report export runs on a worker.
- Country selection displays names; failed loading panels have space for the error and recovery button.

## Evidence and limits

The run's evidence was kept in local, ignored artifacts during review. Those generated files are excluded from the repository and were removed during cleanup. The recorded results are:

- Real campaign state, command receipts, timings, and UI telemetry.
- A captured framebuffer with Budget, Economy, Military, and Unit List.
- The real client and simulation log.
- A passing real Arcade checkbox and text interaction report.

Regression suites cover snapshots, history, infrastructure, data layering, loading, startup, client services, HUD, real server operation, and UI testability. The final combined run contains 86 tests.

Native computer-use window inspection repeatedly timed out waiting for application access. Map mouse navigation and issuing movement orders were therefore not verified. Saving and loading through the visible game UI were not verified in this run; existing user saves were preserved. Multi-day stress testing and the complete set of game mechanics remain outside the verified scenario.

## Follow-up playtest — 2026-10-14

The real client was run from an isolated temporary profile at 1902×991. The user save at `user_data/saves/quicksave` was not used or overwritten. The complete step-by-step plan is in `docs/PLAYTEST_PLAN.md`.

### Verified

- Reached the main menu, started `Open Sandbox` as Ukraine, and loaded `GameView` without system errors.
- Set personal income tax to 35%; the authoritative state reported `personal_income_tax_rate = 0.35`.
- Set speed 5, observed time advance, and paused at 2001-01-04 03:33.
- Opened Military and Unit List; the list displayed Ukrainian units, locations, readiness, and route/status columns.
- Saved `quicksave` in the isolated profile, loaded it through the client, and confirmed the campaign resumed as UKR at 2001-01-04 03:33 with tax 0.35, paused state, speed 5, and zero system errors.
- Resumed at speed 5 and advanced beyond one in-game day, reaching 2001-01-05 19:33. The client continued rendering and no system errors or unrecoverable stall appeared.
- Returned to the main menu and exited via `EXIT TO DESKTOP`; the process exited with code 0.

### Continued playtest — 2026-10-14

- Added map-coordinate `pointer_drag` input to the live UI bridge and used it in the running client. The first drag ended in Donetska, so the game correctly reported that the selected units were already at the destination.
- Repeated the drag to a different region. Nine selected Ukrainian units received queued move orders from Donetska to Cherkaska while their readiness changed from `parked` to `ready`.
- Advanced the simulation until the transition completed. All nine units arrived; the route was Donetska → Dnipropetrovska → Kirovohradska → Cherkaska, and their authoritative coordinates changed to 49.005° N, 29.8575° E.
- Saved the isolated `quicksave`, returned to the menu, and loaded it again. `GameView` resumed at 2001-01-12 07:33 as UKR with 35% income tax and paused at speed 5. After reload, the Unit List still showed the route and Cherkaska destination; no UKR move remained pending.
- Returned to the main menu and exited through `EXIT TO DESKTOP`. The process was no longer running when checked; an exit code was not captured for this continued run.

The continued run's last 240 frame intervals had a median of 16.69 ms, p95 of 25.55 ms, and maximum of 89.21 ms. These are practical diagnostics from the live client, not a performance benchmark. The isolated profile and evidence were removed after review.

The last 240 frame intervals after the simulation run had a median of 16.8 ms, p95 of 34.6 ms, and maximum of 113.6 ms. These include live inspection overhead and are practical diagnostics, not a performance benchmark.

### Findings and limits

- The Open Sandbox panel clearly states that no objectives are assigned. This is consistent with the sandbox mode, but it leaves a first-time player without a suggested first action. An optional starter objective or tutorial path would improve onboarding.
- Several AI covert-cell requests were rejected because no legal route connected their source and destination. The simulation continued normally and `system_errors` remained empty; review whether the AI should filter these attempts before dispatch.
- Drag-to-move and movement persistence are verified for a group of nine co-located units. The orders wait through the two-day readiness transition before movement starts; separate single-unit, invalid-destination, and cancellation cases remain untested.
- Save/load was verified for the campaign date, tax setting, and completed unit destination. Objective-state equality was not compared separately. The existing repository save was not used or overwritten.

The isolated save and generated evidence were removed after review. The existing repository save was preserved.
