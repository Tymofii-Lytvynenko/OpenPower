# Quickstart: UI Journey Test Harness

List available inspection surfaces:

```powershell
openpower ui-test list
```

Run one registered surface using a fixture and interaction journey:

```powershell
openpower ui-test run <surface-id> --fixture tests/ui/fixtures/<fixture>.json --journey tests/ui/journeys/<journey>.json --output artifacts/ui/<surface-id>
```

Run all surfaces at the fixed viewport matrix:

```powershell
openpower ui-test all --matrix --output artifacts/ui
```

Retry only failed runs from the existing suite report:

```powershell
openpower ui-test all --rerun-failed --output artifacts/ui
```

Run the real-runtime input smoke workflow:

```powershell
openpower ui-test live-smoke --output artifacts/ui/live-smoke
```

Run the budget-panel shortcut with its default 1280×1000 viewport:

```powershell
openpower ui-test budget --output artifacts/ui/budget
```

This guide records current command forms and artifact behavior. Commands and live client
acceptance were not executed during the documentation-only specification update.
