# Supplemental national land-use observations

This ledger adds two observations that were absent from the compatible World Bank/FAOSTAT series. The scenario reference year is 2001; each row retains the actual source year and its definition in `national_land_metric_supplement_2001.tsv`.

| Country | Runtime field | Value | Evidence and limitation |
|---|---|---:|---|
| Kosovo (KOS) | Arable land share | 27.3262% | FAO/WFP mission estimated 297,500 ha in 2000. The share divides 2,975 km² by the 10,887 km² territory area printed in the Statistical Yearbook of Yugoslavia 2001; that denominator is attributed to 1953 geodetic data. It is an adjacent-year mission estimate after conflict, and uses total territory area rather than a separately measured dry-land denominator. |
| Montenegro (MNE) | Arable land share | 3.5228% | Monstat's 47,382 ha of 2001 “plough-land and gardens” divided by FAO FRA's 2000 land area of 1,345,000 ha. The observation year is 2001, while the denominator is 2000. The national category is retained as the closest official measure and is not asserted to match FAOSTAT's definition exactly. |
| Taiwan (TWN) | Forest land share | 58.0777% | DGBAS reports 2,101,719 ha forest land and 36,188.04 km² land area in 2001. This exact-year national forestry measure fills the blank field as an alternate definition; it is not assumed equivalent to the harmonized FAO/World Bank forest series. |

The separate [national-park evidence ledger](national_park_terrestrial_2001_evidence.tsv) now includes a conservative Montenegro terrestrial-area inference. The 2001 statistical yearbook reports four parks totalling 908 km², including a 400 km² Lake of Skadar basin park, and a 369.7 km² Montenegro lake surface. Subtracting the full lake surface from that park gives a lower bound of 538.3 km² of terrestrial park area, or 4.0022% of the 2000 land-area denominator. Because the source does not report the park boundary's exact land/water split, the value is explicitly marked as an inference and is not a complete park inventory.

The importer adds these values only where the primary exact-year series is absent. It preserves each source, observation year, scope, and method in the historical metric provenance JSON. The UI should keep the source note visible so these national/mission definitions are not mistaken for a harmonized WDI/FAOSTAT series.

Sources:

- [FAO/WFP Special Report: Kosovo, 24 July 2000](https://www.fao.org/4/x7815e/x7815e00.htm), Table 3 (“Kosovo Land Use”), estimates arable area at 297.5 thousand hectares for 2000. The report explains that 2000 agriculture figures were mission estimates gathered from local agricultural offices, interviews, surveys, and field checks.
- [Statistical Yearbook of Yugoslavia 2001](https://pod2.stat.gov.rs/ObjavljenePublikacije/G2001/Pdf/G20012003.pdf), territorial-area table: 10,887 km² for Kosovo and Metohia, attributed to the Federal Geodetic Administration's 1953 data.
- [Montenegro EU questionnaire, Chapter 11](https://www.questionnaire.eu.me/Chapters/C11.pdf), Monstat land-use table: 47,382 ha of plough-land and gardens in 2001.
- [FAO Global Forest Resources Assessment 2010, Montenegro country report](https://www.fao.org/4/al572E/al572E.pdf), table T1: 1,381 thousand ha total area and 36 thousand ha inland water, yielding 1,345 thousand ha land area for 2000.
