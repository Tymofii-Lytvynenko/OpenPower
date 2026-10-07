# Remaining In-Scope Manual Acceptance Gates

**Updated**: 2026-10-07

This register tracks unfinished acceptance tasks that require a visible running client or coordinated human participants. It does not mark those tasks complete. The game editor and multiplayer remain excluded per [implementation-scope.md](implementation-scope.md); editor-only substeps are not acceptance gates here.

## Current availability evidence

The computer-use surface was queried on 2026-10-07. It returned `apps: []`; Chrome, the Codex in-app browser, and Codex MCP Apps each had no tabs. The active session therefore exposes no running game window for interactive validation. Native application control is disabled in this environment, so headless tests cannot substitute for rendered-client outcomes.

The repository-wide automated suite completed on 2026-10-07 with `pytest -q`: 917 passed, 25 skipped, 239 subtests passed, 116 warnings, and no failures (832.53 seconds). This automated result does not close any rendered-client or participant-based gate listed below.

## Pending gates

| Feature/task | Required in-scope acceptance | Current blocker / scope note |
| --- | --- | --- |
| 001 T012 | Measure live UI frame rate while background simulation advances. | No visible running client. |
| 002 T015 | Exercise route rendering, treaty revalidation, and invasion scenarios in the client. | No visible running client. |
| 006 T009 | Verify pause heartbeat and visible date/speed controls. | No visible running client. |
| 007 T008 | Verify actual globe geometry, picking, and focus behavior. | Headless shader check is not a substitute; no visible running client. |
| 009 T016 | Verify boot/progress rendering, general view transitions, audio continuity, and resize behavior. | No visible running client. Skip editor route/loading portions as out of scope; keep general game-client checks open. |
| 010 T011–T013 | Measure rendered Data Inspector frame time, slider responsiveness, resource charts, and manual dashboard behavior. | These are in-game inspector/dashboard checks; no visible running client. Skip only the editor-view-specific ImGui/ImPlot lifecycle consumer in T008 as out of scope. |
| 106 T021 | Run the globe/camera and battle-visual acceptance matrix. | No visible running client. |
| 106 T022 | Conduct blinded classification with 10 participants and at least 200 judgments. | Requires external human participants and coordination not available in this session. |
| 106 T025 | Measure 100-battle median frame time in the running client. | No visible running client. Three CPU-proxy measurements and the decision to defer optimization are recorded in `106-tactical-battle-visualization/research.md`; do not spend another optimization iteration without a representative in-client profile. |
| 106 T026 | Complete the full automated, visual, UAT, and empirical acceptance flow. | Depends on T021, T022, T025 and a visible client/participants. |
| 109 T014 | Inspect the covert-operations overview and secrecy workflow against the under-30-second criterion. | No visible running client. |
| 110 T019 | Verify the rendered strategic overview, payload selector, launch guidance, and target-defense estimate for SC-006/SC-010. | No visible running client; automated presenter and mocked-panel coverage is recorded in the focused suite. |
| 113 T019 | Run design, training, intelligence-sharing, stale-observation, and mixed-role battle workflows. | No visible running client. |
| 114 T015 | Verify completion time and arrival location through interactive foreign-order UAT. | No visible running client. |
| 115 T017 | Complete interactive battle-overview usability acceptance. | No visible running client. |
| 116 T020 | Complete the 30-second campaign-overview usability check. | No visible running client. |
| 117 T013 | Complete the history/cause-trail workflow and 60-second inspection criterion. | No visible running client. |
| 118 T026 | Verify event feed, response authorization/cost, category-disable boundary, and recovery visibility. | No visible running client. |

## Automated evidence remains distinct

The pending rows above are not evidence of missing implementation by themselves. Automated suites and headless rendering checks remain recorded in each feature's quickstart/research files. Keep each checkbox open until its stated live-client or participant criterion is actually performed and recorded. No editor-only or multiplayer work should be started to close these gates.
