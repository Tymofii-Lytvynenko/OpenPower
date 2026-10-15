# First-Session Client Playtest

- Date: 2026-10-14
- Target: Windows desktop client, local single-player session, base module
- Tester: One operator (functional smoke playtest; not a usability study)

## Goal

Check whether a new player can start the existing Ukraine sandbox, make an economic change, control time, issue a unit movement order, and save and resume the same campaign through the client.

## Safe test profile

Run the client against the isolated temporary project profile `.temp/playtest-20261014-a`. The profile resolves game content from the repository but stores settings and saves under the temporary profile. Do not overwrite the existing `user_data/saves/quicksave`.

## Playthrough

| ID | Action | Pass condition | Evidence |
|---|---|---|---|
| PT-01 | Launch the client and wait for the main menu. | The menu appears after the first usable world snapshot; no startup error is shown. | Client report and screenshot. |
| PT-02 | Start Singleplayer, select Ukraine, and start Open Sandbox. | The game view loads with Ukraine selected and the date visible. | Client report, screenshot, and visible view. |
| PT-03 | Open Economy and Budget, set personal income tax to 35%, and apply. | The UI accepts the value and the authoritative country state reports `0.35`. | Command receipt and game-state report. |
| PT-04 | Set speed 5, let time advance, then pause. | The date advances while running and stops after pause; controls remain responsive. | Before/after date, pause/speed state, frame timing. |
| PT-05 | Open Military and Unit List, choose a deployed Ukrainian unit, and drag it to a visible destination inside Ukraine. | The unit is selectable; a valid movement order produces route/status/ETA feedback and changes authoritative movement state. Record a clear rejection if the chosen destination is invalid. | Screenshot, command result, and unit state. |
| PT-06 | Save with the in-game Save control, return to the menu, then load the isolated quicksave. | Loading returns to the same campaign with date, tax, objective state, and unit movement/location preserved. | Save files, before/after game-state reports, screenshot. |
| PT-07 | Continue through at least one in-game day. | The date advances, snapshots continue arriving, and no system error or unrecoverable stall appears. | Final client report, system errors, frame timing. |
| PT-08 | Return to the main menu and exit using the client UI. | The session shuts down cleanly. | Final client/process status. |

## Stop conditions

- Stop before any save action if the client is not using the isolated profile.
- Stop and record the blocker if the game fails to start, a required control is unavailable, or an action could affect a non-test save.
- Do not infer successful movement or persistence from a dispatched UI event alone; verify the resulting game state after each action.

## Result

Executed on 2026-10-14 with the real Windows desktop client at 1902×991. The UI bridge acknowledged dispatched inputs; every stateful action below was checked in the subsequent client report or screenshot.

| ID | Result | Observation |
|---|---|---|
| PT-01 | Pass | Main menu appeared; no client system errors. |
| PT-02 | Pass | Started Singleplayer → Open Sandbox as UKR; `GameView` became ready. |
| PT-03 | Pass | Applied 35% personal income tax; authoritative state reported `0.35`. |
| PT-04 | Pass | Speed 5 advanced the date to 2001-01-04 03:33. Pause then held the date at that value with speed 5 selected. |
| PT-05 | Pass | Dragged a selected group of 9 Ukrainian units from Donetska to Cherkaska. The units queued while changing readiness from `parked` to `ready`, then arrived along Donetska → Dnipropetrovska → Kirovohradska → Cherkaska. Their authoritative coordinates and route state changed. |
| PT-06 | Pass, partial objective coverage | Saved the completed movement in the isolated `quicksave`, returned to the menu, and loaded it again. The resumed game remained UKR at 2001-01-12 07:33 with tax `0.35`, paused at speed 5; the Unit List showed the saved route and destination after reload. Objective-state equality was not compared separately. |
| PT-07 | Pass | The simulation advanced from 2001-01-04 03:33 to 2001-01-12 07:33, including the readiness transition and movement. No system errors or unrecoverable stall appeared. Last 240 frame intervals: median 16.69 ms, p95 25.55 ms, max 89.21 ms (diagnostic only). |
| PT-08 | Pass, exit code not captured | Returned to the main menu and selected Exit to Desktop. The client process was no longer running when checked. |

### Findings for the next iteration

- Open Sandbox explicitly says that no objectives are assigned. That is clear, but a new player still has no suggested first action; consider an optional starter objective or tutorial path.
- The drag bridge and group movement flow are now verified. This run tested a same-region drop (reported “already at the destination”) followed by a valid route to Cherkaska; single-unit selection and invalid-destination feedback still merit separate coverage.
- The existing repository save was preserved. The isolated test save contained the completed movement at the end of the run; the temporary profile was removed after review.

Client evidence was collected under `.temp/playtest-20261014-a/artifacts-1902/` (`report.json`, `actual.png`, and command receipts) and removed after review; generated artifacts are not committed.
