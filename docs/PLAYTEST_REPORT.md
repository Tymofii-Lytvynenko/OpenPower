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
