# FAOSTAT 2001 land-metric candidates

This evidence ledger records seven FAOSTAT Land Use (RL) source values for 2001. Five reviewed blank fields are imported through `faostat_land_metric_supplement_2001.tsv`: Sudan land area, arable-land share, and forest share; Taiwan arable-land share; and Vatican land area. Tuvalu forest is comparison-only because the historical table already contains that value. Taiwan land area is excluded because it conflicts with the existing total-area and water-area pair.

The source archive is `faostat_land_use_2026.zip`, last modified 2026-10-02, with SHA-256 `39b739fbfb694971207a2efa572c41e8de2386fc5cb33caaf2a188e9c9a6ca3f`. Its official catalog is [FAOSTAT Land Use (RL)](https://www.fao.org/faostat/en/#data/RL). Values are selected only from observation year 2001. FAOSTAT flags mean: `A` official value, `I` value imputed by a receiving agency.

## Candidate values

| Game ID | Field | Value | Source basis | Caveat |
|---|---|---:|---|---|
| SDN | Land area | 2,376,000 km² | `Sudan (former)`, M49 736, 2001 Land area, flag A | The source's historic boundary includes the territory now represented by SSD; this matches the existing 2001 Sudan total-area minus inland-water difference. |
| SDN | Arable land | 6.8923% of land area | 16,376 / 237,600 thousand ha, flags I/A | The arable-land numerator is imputed by FAOSTAT's receiving agency. It describes pre-partition Sudan, including present-day South Sudan. |
| SDN | Forest area | 14.0051% of land area | 33,276.16 / 237,600 thousand ha, flags I/A | The forest-area numerator is imputed by FAOSTAT's receiving agency. It describes pre-partition Sudan, including present-day South Sudan. |
| TWN | Land area | 35,410 km² | `China, Taiwan Province of`, M49 158, 2001 Land area, flag A | The archive's country-area value is 35,960 km², while the existing Factbook total-area value is 35,980 km². Keep the existing surface-area field and do not derive inland water from the mismatched source pair. |
| TWN | Arable land | 17.5312% of land area | 620.78 / 3,541 thousand ha, flags I/A | The arable-land numerator is imputed by FAOSTAT's receiving agency. |
| TUV | Forest area | 34.3333% of land area | 1.03 / 3 thousand ha, flags I/A | Comparison-only: the current historical row already contains this value. The numerator is imputed by FAOSTAT's receiving agency. |
| VAT | Land area | 0.44 km² | `Holy See`, M49 336, 2001 Land area, flag A | The archive reports country area and land area both as 0.044 thousand ha. |

All area conversions use `1 thousand hectares = 10 km²`; percentage fields are numerator area divided by FAOSTAT land area times 100. The exact raw values, flags, denominators, source country codes, and implementation status are preserved in `faostat_land_metrics_candidates_2001.tsv`; the reviewed import subset and scope notes are in `faostat_land_metric_supplement_2001.tsv`.

## Deliberately excluded gaps

- Antarctica has no national agricultural-land definition in this source.
- Kosovo, Montenegro, and Serbia are absent as separate 2001 source units; FAOSTAT reports the combined `Serbia and Montenegro` row, which cannot be divided among the three game entities without a separate subnational source.
- FAOSTAT's M49 736 `Sudan (former)` row is retained as the 2001 Sudan boundary and is not assigned to SSD separately.
- FAOSTAT does not publish a separate 2001 forest-area row for Taiwan or a separate arable-land row for Tuvalu, Monaco, or Vatican City. Missing entries are not inferred as zero.
- Other candidate fields were left untouched where the current historical table already has a value or where the source denominator conflicts with an existing country total.
