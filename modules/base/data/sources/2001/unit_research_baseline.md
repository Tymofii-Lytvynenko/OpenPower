# Unit research baseline (2001)

`modules/base/data/countries/countries_unit_research_2001.tsv` supplies a modeled
starting value for each of the 12 Unit Research characteristic meters for all
199 country entries. The static country loader merges the file into the country
table by ISO country ID. Regenerate it with:

```powershell
python utils/generate_unit_research_baseline_2001.py
```

## Meaning and limits

The values are low-confidence, relative capability factors for the OpenPower
unit-role archetypes. They are **not** historical weapon specifications,
measured national technology ceilings, or military R&D observations. The
available public historical data do not provide per-country, per-characteristic
technology ceiling values for the full game roster.

The 12 columns correspond to Gun Range, Gun Precision, Gun Damage, Missile
Range, Missile Precision, Missile Damage, Missile Payload, Speed, Sensors,
Armor, Stealth, and Countermeasures. Each factor is used as the display value
for the matching 2001 modeled baseline meter. Its role is to give the interface
a traceable, explicit estimate while preserving the distinction between an
archetype's modeled capability and a documented equipment specification.

## Formula

For each country, the generator calculates the national index as:

```text
T = clamp(0.45 + 0.50 * HDI_2001 + 0.10 * OpenPower_research_budget_ratio, 0.35, 0.98)
factor(characteristic) = floor(characteristic) + T * (1 - floor(characteristic))
```

The characteristic floors are copied from `BootstrapSystem._country_unit_capabilities`;
this keeps the data aligned with the existing unit capability model. The HDI
input is `countries_historical.tsv.reference_human_dev`, and its source
category is carried through from `reference_human_dev_status`; this may be a
retrospective value, an older published value, an estimate, or an explicitly
labeled proxy. When no historical HDI value exists, the generator falls back
to `countries_dem.tsv.human_dev`, which uses the neutral 0.50 simulation value
for non-applicable/unreported cases; 0.45 is a last-resort proxy only when that
field is missing. The research-budget ratio is an OpenPower scenario setting,
**not** a historical R&D percentage; the 0.10 default is used only when the
setting is absent. Source category, availability, and model definition are
retained on every output row.

HDI is a broad development proxy and does not establish military research
capacity. This model does not infer that countries with the same factor fielded
the same weapon systems. Its confidence is therefore marked `low` throughout.

## Sources

- [UNDP Human Development Report data center](https://hdr.undp.org/data-center/documentation-and-downloads) — retrospective 2001 HDI series cached in `undp_hdr2025.csv` and imported into `countries_historical.tsv`.
- [World Bank WDI R&D expenditure metadata](https://databank.worldbank.org/metadataglossary/world-development-indicators/series/GB.XPD.RSDV.GD.ZS) — documents that the public indicator is economy-wide GERD, not defense R&D. It is not used as a military technology measurement in this model.
- [SIPRI Military Expenditure Database](https://www.sipri.org/databases/milex) — historical defense spending series; it does not disaggregate national spending into the 12 per-characteristic research fields, so it is not treated as direct evidence for these values.
- `modules/base/systems/world/bootstrap_system.py` — existing scenario technology-index and characteristic-scaling formula reproduced by the generator.

## Interface binding

The Technology tab reads the matching modeled country factor and labels it as
an estimate. Progress and Funding remain authoritative OpenPower branch values:
each is echoed across that branch's characteristic slots because this simulation
tracks progress and funding at branch level, not per characteristic. Strategic
Program, Weapons, and Defense continue to map to their existing three branch
tracks. A visible tooltip describes these shared branch proxies.
