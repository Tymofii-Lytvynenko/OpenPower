# Contract: Unit Rendering and Interaction

## Atlas contract

- Each flag has an RGBA 32×22 interior placed inside a 2 px transparent border.
- Atlas cells use deterministic owner ordering; entries expose normalized UV bounds for the interior only.
- Sampling uses linear filtering; CPU resizing uses Lanczos when Pillow exposes that resampler.
- Unknown or missing tags resolve to the `XXX` image, otherwise to opaque magenta.
- Adding owners rebuilds the atlas with the union of old and new tags and publishes a usable replacement texture only after upload succeeds.

## Batch contract

- For N valid billboards, vertex generation emits 6N vertices with screen position, UV, and color.
- A nonempty normal batch binds the atlas texture once and submits one geometry draw; empty/invalid dimensions are safe no-ops.
- GPU initialization or submission failures return false so the existing ImGui flag renderer can draw instead.
- Overlay visuals (selection, routes, badges, drag, and rectangle) remain available whether or not the GPU batch succeeds.

## Interaction contract

- Left-click selects a visible unit; a drag gesture resolves destination region and geographic coordinates before sending action(s).
- Box selection uses normalized rectangle bounds and includes intersecting billboards.
- Multi-unit move actions are dispatched in stable unit-ID order as `ActionMoveUnit`; invalid map targets do not send an action.
- The controller reads renderer/map interfaces and sends actions through the network client; it never writes simulation state.

## Performance/visual gates

- Mocked call-count test: 200 units → one texture bind call and one geometry draw.
- Live acceptance: adding a mod owner rebuilds within 15 ms on recorded hardware/runtime; edge sampling shows no neighboring-color bleed.
