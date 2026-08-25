# Battle Visualization Contract

This is the presentation contract between the authoritative snapshot and the client map. It is intentionally read-only: rendering a battle MUST NOT dispatch a command or mutate a world table.

## Input contract

For each battle row in the current `GameState` snapshot, the renderer may consume:

- `id`, `region_id`, `mode`, `status`, `round`, `started_at_minute`, and `concluded_at_minute`;
- `anchor_latitude`, `anchor_longitude`, and `anchor_source` when present;
- `attacker_side` and `defender_side` for side-level visual identity;
- the current camera matrices and the client presentation time.

If anchor columns are absent in a legacy snapshot, the renderer resolves the region center. It does not inspect visible unit billboards to relocate the effect.

## Mode and label contract

| Authoritative `mode` | User-facing label | Required visual pattern |
|---|---|---|
| `positional` | Passive | Restrained pulse/paired halos; no directional assault cue. |
| `assault` | Active | Stronger pulse, directional side exchange, and bounded impact cue. |

The battle overview and map marker MUST use the same mapping. They MAY show the raw value in secondary text for diagnostics, but they must not invent a different mode.

## Lifecycle contract

- `active`: render the mode-specific combat effect and persistent state marker.
- `stalemate`: stop the combat loop and render only the restrained lifecycle marker.
- `concluded`: stop combat animation immediately after the authoritative update; an optional conclusion indicator is non-interactive and expires within one second of its local presentation start.
- Unknown status: render a persistent fallback marker and omit motion rather than raising an overlay-wide error.

## Projection and occlusion contract

The effect is projected from the geographic anchor on every camera change. The shared globe projection MUST:

1. reject back-facing anchors;
2. return silhouette clearance for front-facing anchors and reject exchange geometry that would cross the longitude seam;
3. keep marker dimensions in bounded screen-space pixels rather than scaling them with globe radius;
4. return a stable draw order for identical battle IDs, camera inputs, and presentation time;
5. retain a bounded static marker for every front-facing anchor and omit any decorative halo, flash, or exchange segment whose complete footprint exceeds the returned silhouette clearance. A geographic point marker has no longitude-seam span; exchange segments must never connect across the hidden hemisphere.

## Side identity contract

Exactly two visual side identities are produced from `attacker_side` and `defender_side`. Allied participants inherit their side identity. A missing or invalid side color falls back to the existing deterministic political-color generator. Side colors are presentation data and do not alter country or flag records.

## Timing contract

`BattleEffectRenderer.render(state, presentation_total_minutes, reduce_motion)` evaluates a pure deterministic phase using a stable digest of battle identity. The phase advances between snapshots using the client presentation clock and is independent of network arrival time and Python's randomized process hash. With `reduce_motion=True`, the renderer keeps the marker and labels but freezes the phase and suppresses flashes/movement.

## Overlap contract

Stable battle-ID order is cached by battle revision. Visible footprints are inserted into a screen-space grid whose cell size is at least the maximum bounded footprint diameter, and collision checks are limited to the same and neighboring cells. Each label/decorative effect receives the first available offset from a fixed ordered candidate set. A small mark and leader remain at each exact projected anchor. Identical battle rows, camera inputs, and presentation time therefore produce identical placement without rewriting authoritative coordinates.

## Cache contract

Normalized battle inputs, stable order, region lookup, and side palettes may be cached by their table revisions. Camera projection, silhouette clearance, phase, and collision-grid membership are recalculated only for visible candidate anchors. All effects are submitted through one no-input overlay draw list; the cache never mutates authoritative state.

## Visibility and failure contract

- A valid battle anchor remains eligible for drawing when unit owners are filtered or unit billboards are absent.
- A missing participant list does not hide a battle that has a valid anchor.
- A missing/invalid anchor falls back to `region_id` and the region center.
- One malformed battle row is isolated; other battle effects and normal map rendering continue.
- The renderer does not allocate one animated object per unit, shot, or combat calculation.

## Compatibility contract

The existing snapshot transport remains valid because battle anchors are ordinary additive table columns. Older snapshots are accepted through schema defaults. Server state remains authoritative for battle identity, mode, anchor, lifecycle, and outcome; the client owns only transient presentation phase.
