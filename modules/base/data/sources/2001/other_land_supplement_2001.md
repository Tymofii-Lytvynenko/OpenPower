# 2001 Other land gap supplement

This supplement adds separately namespaced scenario estimates for two rows whose
game territory can be reconciled to the cached 2001 FAOSTAT Serbia-and-Montenegro
aggregate: Montenegro and Serbia including Kosovo. It does not overwrite the
primary `countries_historical.other_land_pct` series. The generated extension is
`modules/base/data/countries/countries_other_land_supplement_2001.tsv`.

Regenerate with:

```powershell
.venv\Scripts\python.exe utils/generate_other_land_supplement_2001.py
```

Add `--check` to verify the checked-in table without writing it. Raw source facts
and scope decisions are listed in `other_land_supplement_inputs_2001.tsv`.

## FAOSTAT definition and aggregate check

The cached FAOSTAT Land Use snapshot records, for Serbia and Montenegro in 2001,
10,200,000 ha of land area (flag `A`), 5,592,000 ha of agricultural land
(flag `A`), 3,168,980 ha of forest land (flag `I`), and 1,439,020 ha of Other
land (flag `I`). The categories reconcile exactly:

```text
10,200,000 - 5,592,000 - 3,168,980 = 1,439,020 ha
```

Flag `I` means FAOSTAT marks the value as imputed by a receiving agency. The
generator reads the source archive, checks the archived values against the
source ledger, and verifies this residual before deriving country rows.

## Derived rows

### Montenegro (MNE)

FAO's 2010 Montenegro country report gives a 2000 land area of 1,345,000 ha,
derived from total area of 1,381,000 ha minus 36,000 ha of inland water. The same
report gives 543,000 ha of forest for 2000 and explains that its 1990–2010 forest
series carries a 2007 MCPFE figure without forecasting. A World Bank 2003
comparative-statistics annex reports 517,830 ha of agricultural land and cites
the Statistical Yearbooks of Yugoslavia and Montenegro (2001), but does not state
the observation year for this row.

The low-confidence scenario residual is:

```text
1,345,000 - 517,830 - 543,000 = 284,170 ha
284,170 / 1,345,000 * 100 = 21.1279%
```

This is a mixed-period national residual estimate, not an exact 2001 measured
FAOSTAT value. The FAO FRA forestry table's own `Other land` category is not
substituted: it uses the forestry classification of forest, other wooded land,
and other land, which differs from the FAOSTAT Land Use item used here.

### Serbia (SRB)

The game SRB land row includes Kosovo and excludes Montenegro. The 2001
FAOSTAT aggregate includes both the territory represented as SRB and Montenegro.
Subtracting the Montenegro estimate above gives the SRB scope:

```text
Other land: 1,439,020 - 284,170 = 1,154,850 ha
Land area: 10,200,000 - 1,345,000 = 8,855,000 ha
Share: 1,154,850 / 8,855,000 * 100 = 13.0418%
```

The row is a low-confidence derived split. It inherits the FAOSTAT `I` flag on
forest and Other land, and the mixed 2000/2001 Montenegro inputs. Kosovo is
included in this Serbia scope and cannot also receive a separate residual from
the aggregate.

## Other missing IDs and separate alternative

- **ATA:** not applicable as a country-level land-use denominator.
- **KOS:** not independently split from the 2001 Serbia-and-Montenegro land-use
  aggregate. The statistical yearbook has a territorial area, but comparable
  agricultural and forest components for a residual are absent. The CIA 2018
  Factbook separately reports Kosovo `other` at 5.5% (2001 estimate); the
  extension exposes it as a non-comparable CIA category and does not treat it
  as a FAOSTAT residual or as a Serbia/Kosovo area split.
- **SSD:** South Sudan was part of Sudan in 2001; no compatible territorial split
  of the Sudan land-use inputs is available.
- **TWN:** the 2001 CIA Factbook reports `other: 15%` of land use for Taiwan,
  including Pescadores, Matsu, and Quemoy. CIA's `other` category includes
  permanent pastures, forests and woodland, built-on areas, roads, and barren
  land. This is not FAOSTAT's Other land residual, so it is stored only in the
  distinct `scenario_cia_land_use_other_2001_*` columns. The FAOSTAT-comparable
  field remains unavailable for TWN.

The CIA alternatives for KOS and TWN are shown only as source-labeled context.
They do not replace the FAOSTAT-compatible field or resolve the unresolved
Serbia/Kosovo aggregate boundary.

## Sources

- FAOSTAT Land Use (release 2026-10-02, cached local archive and manifest):
  <https://www.fao.org/faostat/en/#data/RL>
- FAO, *Global Forest Resources Assessment 2010 — Montenegro Country Report*,
  Table T1 and methodology notes:
  <https://www.fao.org/4/al572E/al572E.pdf>
- World Bank, *Republics of Serbia and Montenegro: Agriculture Sector Review*,
  Annex 3, Table 1:
  <https://documents1.worldbank.org/curated/en/818271468760747059/pdf/288030YF0Ag0sector0review01public1.pdf>
- CIA, *The World Factbook 2001*, Taiwan entry, archived by Project Gutenberg:
  <https://www.gutenberg.org/ebooks/27638>
- CIA, *The World Factbook 2018*, Kosovo, “Land use”:
  <https://johnmeister.com/FACTS/WORLD-FACTBOOK-2018/geos/kv.html>
- Statistical Yearbook of Yugoslavia 2001, territorial-area reference for
  Kosovo:
  <https://pod2.stat.gov.rs/ObjavljenePublikacije/G2001/Pdf/G20012003.pdf>
- United Nations, South Sudan member-state profile:
  <https://www.un.org/en/about-us/member-states/south-sudan>
