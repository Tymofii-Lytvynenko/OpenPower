# Data Model: Treaty and Diplomatic Map Overlay

## Authoritative tables

- `countries_treaties`: one row per treaty; list or side-based membership, treaty `type`, optional `status`, optional `suspended_members`, and optional `expires_at_minute`.
- `countries_wars`: one row per war; `side_a`, `side_b`, optional `status`. Legacy static rows without status represent active wars.
- `regions`: `id` maps to a geographic region; `owner` is legal sovereignty and `controller` is current control.

All client summaries/color maps are derived views. The renderer caches only a non-authoritative grouping of region IDs by unchanged controller/owner pairs; it does not modify the source tables.

## Palette classification

For the selected country perspective: selected sovereign/controller is green; active unsuspended treaty allies are blue; active enemies are red; neutral countries are charcoal; occupied territory is orange; pending annexation claims use a separate dark green; missing control is muted unknown. Occupation and selected-country status are resolved before alliance/enemy colors; war enemies take precedence over alliance membership for non-selected countries.

## GPU palette transition

The lookup texture remains a dense-ID RGBA array. During mode/focus changes, the prior visible LUT is retained alongside the target LUT. A normalized transition uniform advances from 0 to 1 and controls eased shader interpolation; selection tint reads the current target palette so selection feedback remains immediate.
