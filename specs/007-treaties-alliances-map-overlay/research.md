# Research: Treaty and Diplomatic Map Overlay

## Codebase findings

1. `StaticAssetLoader` merges `data/world/*.toml` using each file stem as the root TOML key. The treaty file follows this contract, but the war file used `[[wars]]`, so no `countries_wars` table was loaded from base content.
2. Dynamic diplomacy is managed by `modules/base/systems/world/treaty_diplomacy.py`; it creates active treaty/war rows and stores suspended treaty members and expiration minutes where applicable.
3. `EmpireMapMode` already provides selected, ally, enemy, neutral, occupied, pending-annexation, and unknown colors. Its readers must ignore ended/expired agreements and suspended members while retaining legacy rows with no status field as active.
4. `ViewportController` invalidates map-mode colors by relevant table revisions and selected focus. Region ownership/controller values often remain unchanged over population ticks, so grouping region IDs by political pair can safely be cached by those immutable columns.
5. `TextureManager` currently writes a single RGBA lookup texture and `globe.frag` applies it directly. A second lookup texture and a transition uniform provide a GPU-side blend without a second per-fragment region-data lookup.
6. The repository's 4,559-region fixture meets the current 2 ms color-calculation gate when unchanged political groups are reused; repeated alternating focus measurements are included in the opt-in test.

## Decisions

- Name TOML list roots after their filenames so generic loading produces the expected world table.
- Treat rows without a status as active for backward compatibility; explicit non-active status, expired minute, or suspended membership removes the corresponding diplomatic color relationship.
- Give active enemies precedence over alliances in map color resolution when a country is simultaneously an ally and a belligerent, because current war state is the relevant visual signal.
- Keep occupation/controller color distinct from treaty affinity and derive it from canonical region ownership/controller columns.
- On palette change, snapshot the currently visible blend, upload previous and target LUTs, and ease between them in GLSL. This prevents a quick second mode change from snapping back to an earlier palette.
- Reuse grouped region IDs only while the ordered ID/owner/controller columns remain equal; country population or economy columns do not invalidate the grouping.
- Keep on-screen globe and interactive-picking acceptance as a manual gate. An opt-in live GPU check now compiles the production globe vertex/fragment pair and exercises the production fragment shader against a one-pixel framebuffer; it does not claim to validate the running scene or input path.

## Live GPU shader evidence

`RUN_MAP_RENDERER_GPU_CHECKS=1` runs `test_live_globe_shader_compiles_and_renders_transition_borders_and_selection`. On Windows with NVIDIA GeForce RTX 5060 Ti, OpenGL 4.6.0 NVIDIA 591.74, the production shader pair compiled and the fragment shader returned previous `(0, 0, 200)`, midpoint `(100, 0, 100)`, target `(200, 0, 0)`, non-border red `200`, border red `120`, and selected `(255, 161, 161)`. This closes the shader/pixel behavior portion only; interactive focus selection and globe presentation remain a separate acceptance gate.
