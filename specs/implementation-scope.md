# Repository Specification Implementation Scope

Implement and validate the repository specifications in `specs/001` through `specs/118`, excluding multiplayer (`specs/102`) and game-editor-only functionality. There is no single editor-only feature directory, so the editor exclusion applies to editor-specific requirements embedded in otherwise in-scope features; the remaining gameplay requirements in those features stay in scope.

Editor-only work excluded from future implementation and acceptance:

- `specs/001-ipc-multi-process-architecture`: the special `SAVE_MAP_CHANGES` editor command.
- `specs/009-client-view-state-controller-ui`: editor initialization/loading routes and editor-only acceptance; general game-view navigation, loading, and client lifecycle remain in scope.
- `specs/010-imgui-dashboard-inspector-panels`: the editor-view-specific ImGui/ImPlot lifecycle consumer; shared UI context behavior and in-game inspector/dashboard panels remain in scope.
- `specs/011-map-rendering-pipeline-shaders`: planar map projection selection and rendering in the map editor; the common renderer, shader bundles, and gameplay map path remain in scope.

Existing editor code is preserved. This scope note does not authorize deleting or disabling it; it only excludes implementing or validating editor functionality as part of specification convergence.

## Performance policy

Functional specification coverage takes priority over optimization. Record performance failures and unresolved scan/workload debt for later. For any algorithm that fails its specified performance gate, allow at most three measured optimization iterations. If it still fails after iteration three, record each change and measured outcome, mark the remaining issue for future work, and continue to other specifications.
