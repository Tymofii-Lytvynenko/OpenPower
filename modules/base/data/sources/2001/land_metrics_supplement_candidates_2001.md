# Supplemental 2001 land-metric candidates and review items

This is a review ledger for country-specific land evidence. Montenegro's 2000 land area, inland-water area, and forest share are approved as explicitly dated adjacent-year values and imported through `faostat_land_metric_supplement_2001.tsv`. Rows with a `scope_review` or `candidate_review` status remain outside runtime data.

## Kosovo and Serbia boundary review

The official Statistical Yearbook of Yugoslavia 2001 lists Kosovo and Metohia at 10,887 km² in its territorial area table. It states that area data came from the Federal Geodetic Administration (1953), so the 2001 yearbook is a reference publication, not a new 2001 geodetic survey. The EU/Commission statistical annex independently reports Kosovo's total area as 10,887 km² for 2001. CIA's 2018 archived Kosovo profile labels arable land (27.4%) and forest (41.7%) as 2001 estimates.

These three values are preserved as scoped candidates, not import recommendations. The current historical SRB row has a total area of 88,360 km², while Serbia proper excluding Kosovo is about 77,474 km² in the World Bank agriculture review and the 2001 Yugoslav yearbook's Serbia area includes Kosovo. Adding KOS area as a separate row without revisiting SRB would overlap territory. The CIA 2001 edition had one Yugoslavia profile and no separate Kosovo country profile; the 2018 estimates are retrospective. Do not split or add values without deciding whether SRB should represent Serbia proper or Serbia including Kosovo.

Sources:

- [Statistical Yearbook of Yugoslavia 2001](https://pod2.stat.gov.rs/ObjavljenePublikacije/G2001/Pdf/G20012003.pdf), area table and source note (Federal Geodetic Administration, 1953).
- [EU statistical annex for Kosovo under UNSCR 1244](https://www.ecoi.net/en/file/local/1004850/1226_1292238983_ks-rapport-2010-en.pdf), total area table includes 2001.
- [CIA World Factbook 2018 Kosovo archive](https://www.thefactbook.org/kosovo/2018), retrospective 2001 land-use estimates.

## Montenegro land, water, forest and arable evidence

FAO's Montenegro FRA 2010 country report gives 2000 area table values: total 1,381 thousand ha, inland water bodies 36 thousand ha, forest 543 thousand ha. The land area is therefore 1,345 thousand ha (13,450 km²), and inland-water area is 360 km². Total area converts to 13,810 km², matching the current historical row. These geography values are one year before the scenario and the report holds the same area figures for 1990, 2005 and 2010, supporting use as stable-boundary geography if the scenario accepts 2000 as the nearest available observation.

The official Government of Montenegro EU questionnaire cites Monstat data and reports 47,382 ha of arable land and gardens / plough-land and gardens in 2001. Dividing by the 2000 FAO land denominator produces 3.5228%, but the national category may not exactly match FAOSTAT's arable-land definition. It remains for review, not as a fully comparable value. The FAO FRA forest measure gives 40.3717% for 2000 and is imported with observation year 2000 retained in provenance.

Sources:

- [FAO FRA 2010 Country Report: Montenegro](https://www.fao.org/4/al572E/al572E.pdf), table T1.
- [Government of Montenegro EU questionnaire, Chapter 11](https://www.questionnaire.eu.me/Chapters/C11.pdf), 2001 national agricultural categories and Monstat source note.
- [World Bank land-area definition](https://databank.worldbank.org/metadataglossary/world-development-indicators/series/AG.LND.TOTL.K2), confirming land area excludes inland water bodies.

The Kosovo and Montenegro arable rows remain staged and non-runtime. The row-level evidence, observation years, formulas, statuses and confidence labels are in `land_metrics_supplement_candidates_2001.tsv`; imported rows are in `faostat_land_metric_supplement_2001.tsv`.
