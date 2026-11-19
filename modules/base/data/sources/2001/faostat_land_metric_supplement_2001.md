# Imported 2001 land metric supplements

This import-ready ledger fills only blank historical cells. The importer keeps World Bank observations when present and records each supplemental observation year in `historical_metric_provenance_json` and `provenance.tsv`.

| Country | Field | Value | Observation year | Source caveat |
|---|---|---:|---:|---|
| Sudan (former) | Land area | 2,376,000 km² | 2001 | Official FAOSTAT value for the pre-partition boundary, including present-day South Sudan. |
| Sudan (former) | Arable land | 6.8923% | 2001 | FAOSTAT-imputed numerator; official land-area denominator; pre-partition boundary. |
| Sudan (former) | Forest area | 14.0051% | 2001 | FAOSTAT-imputed numerator; official land-area denominator; pre-partition boundary. |
| Taiwan | Arable land | 17.5312% | 2001 | FAOSTAT-imputed numerator; official land-area denominator. |
| Vatican City | Land area | 0.44 km² | 2001 | Official FAOSTAT value; no inland water is inferred. |
| Montenegro | Land area | 13,450 km² | 2000 | FAO FRA table; one-year-earlier observation; matches its 13,810 km² total area minus 360 km² inland water. |
| Montenegro | Inland water | 360 km² | 2000 | FAO FRA table; one-year-earlier observation retained as 2000. |
| Montenegro | Forest area | 40.3717% | 2000 | FAO FRA 2000 forest area divided by 2000 land area; source release published in 2010. |

The source dataset and complete calculation are retained per row in `faostat_land_metric_supplement_2001.tsv`. FAOSTAT's official catalog is [Land Use (RL)](https://www.fao.org/faostat/en/#data/RL). Its flags distinguish official values (`A`) from values imputed by a receiving agency (`I`). Montenegro's adjacent-year values cite the [FAO Global Forest Resources Assessment country report](https://www.fao.org/4/al572E/al572E.pdf), table T1. The source-ledger review and excluded boundary-sensitive candidates are summarized in [the land metric review notes](land_metrics_supplement_candidates_2001.md).

Kosovo area and land-use candidates remain excluded because the current Serbia total includes Kosovo. Montenegro's 2001 plough-land/gardens figure remains excluded because its category does not establish equivalence with FAOSTAT's arable-land definition. Taiwan land area remains excluded because its paired total and inland-water figures do not match the existing country surface-area record.
