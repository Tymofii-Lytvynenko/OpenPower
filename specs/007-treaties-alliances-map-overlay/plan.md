# Implementation Plan: Treaty and Diplomatic Map Overlay

**Branch**: `007-treaties-alliances-map-overlay` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

## Summary

Use the existing static-data loader and canonical treaty/war tables as the diplomacy source of truth. Keep dynamic diplomatic lifecycle in `DiplomacySystem`; derive perspective colors in the client map-mode strategy; upload region palettes through the texture manager; and render both palettes in the globe fragment shader during a short, eased transition. Preserve the current map picking and passive-client boundaries.

## Technical Context

**Runtime**: Python 3.14, Polars, Arcade/OpenGL, GLSL 330.
**Persistent state**: `countries_treaties`, `countries_wars`, `regions.owner`, and `regions.controller`.
**Presentation path**: `ViewportController` → `EmpireMapMode` → `TextureManager` LUT textures → `MapRenderer` fragment shader.
**Tests**: data-loader contracts, deterministic map-mode classification, viewport refresh invalidation, lookup texture interpolation, and opt-in full-region color timing.
**Performance goal**: recompute colors for all 4,559 regional fixture rows after focus changes in under 2 ms.
**Visual gate**: the production globe shader pair now compiles on the NVIDIA/OpenGL driver, and an opt-in framebuffer test verifies the production fragment shader's palette transition, border darkening, and selection tint. Rendering the actual globe scene and validating interactive picking/focus still require a running desktop-client check.

## Constitution Check

- **Layering**: PASS. Static loading stays server-side; client map modes/rendering remain presentation-only.
- **Canonical data**: PASS. Existing tables remain authoritative; no client diplomacy state is introduced.
- **Composition**: PASS. Map modes retain the strategy interface; texture interpolation is isolated in `TextureManager`.
- **Commenting**: PASS. Cache and interpolation comments explain performance and continuity reasons.
- **Empirical verification**: PARTIAL. Headless behavior, performance gates, and actual-driver fragment-shader pixels pass; interactive globe appearance and picking remain unverified.

## Design Outputs

- [research.md](research.md) documents the loader naming mismatch, live diplomacy representation, and renderer constraints.
- [data-model.md](data-model.md) records the table and palette invariants.
- [contracts/treaty-map.md](contracts/treaty-map.md) defines the client/server rendering boundary.
- [quickstart.md](quickstart.md) lists deterministic and empirical verification commands.
- [tasks.md](tasks.md) tracks completed code/tests and outstanding interactive confirmation.
