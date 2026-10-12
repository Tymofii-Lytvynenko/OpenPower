# Data Model: Mod Data Chaining Engine

## ModManifest

One discovered module descriptor.

| Field | Type | Validation / meaning |
| --- | --- | --- |
| `id` | string | Unique module identifier; used for dependency edges and lookup. |
| `name` | string | Human-readable display name. |
| `version` | string | Module content version. |
| `api_version` | integer | Must match the engine module API before registration. |
| `dependencies` | ordered list of strings | Required module IDs; all must resolve and precede the dependent. |
| `path` | `Path` | Module directory containing manifest, data, assets, and optional registration. |
| `min_engine_version` | optional semantic version | Inclusive lower compatibility bound. |
| `max_engine_version` | optional semantic version | Inclusive upper compatibility bound. |

## ModLoadChain

An ordered list of validated `ModManifest` entries. Requested mods are roots; transitive prerequisites are included once. Each dependency precedes its dependent, and tie ordering is deterministic. The chain drives data-directory enumeration, runtime contribution order, and asset/localization precedence.

## Layered DataFrame

A named world table composed from base through active dependency layers. Merge identity is inferred from shared columns: `hex`, `id`, or `(source, target)` where available. Child values override earlier non-null values for matching identities; missing fields and unrelated rows remain intact. When no stable key exists, layers concatenate using relaxed schema union rather than destructive replacement.

Within a keyed merge path, duplicate extension records collapse to one record per key. For conflicting non-null values from child layers, higher-priority values win; a null child value preserves the preceding value. The loader must not duplicate the corresponding master entity as a side effect of a repeated extension key.

## Country identity profile assets

Language and religion profiles are loaded separately from `modules/<id>/data/countries/country_languages.toml` and `country_religions.toml`. The active chain is traversed in precedence order. A valid nonempty profile replaces the complete prior profile for the same `(identity_type, country_id)`; a country omitted by a child layer retains its inherited profile. Rows for countries absent from the loaded world and non-finite or non-positive shares are skipped. Each accepted profile is normalized to 100%. The runtime records the bundled filename as `source_reference`, the bundled estimate label as `source_name`, a caveat in `source_note`, and source year `0` when the original source year is unknown.

## Runtime Contribution

An ordered module contribution containing systems, table schemas, and save migrations. System IDs are unique within a module; a higher-priority mod may intentionally replace an earlier system ID, while duplicate IDs from the same mod are rejected. Schemas and migrations retain their existing registries and version checks.

## Asset and localization overlays

- Assets resolve from highest-priority active mod toward the base fallback.
- Localization JSON merges from base to child; later values override identical keys while unrelated translations remain.
- Locale names are filename-safe and each catalog must map string keys to string values.
