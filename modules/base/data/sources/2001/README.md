# Historical scenario observations

Regenerate with `.venv/Scripts/python.exe utils/import_historical_country_data.py`.
The importer caches source responses and never substitutes a later observation year.

## Military equipment inventory

`military_equipment_inventory_supplement_2001.tsv` records three source-backed
role counts for 2001: Russia's 17 operational ballistic-missile submarines
(Bulletin of the Atomic Scientists, May 2001), China's zero aircraft carriers
(CRS, 12 November 2001), and India's one aircraft carrier in service (Lok Sabha
answer, 15 March 2001). The Indian answer explains that the offered Admiral
Gorshkov still required repair and modernization before it could enter service;
the approved indigenous ship was not yet available. Each cited statement covers
the full count for its matching role on the source date. It does not substantiate
other equipment roles or countries. Run `python
utils/import_military_equipment_supplement_2001.py` after inventory generation
to apply just these ledger rows; add `--check` to validate the table without
writing it.

Sources:

- World Development Indicators, observations dated 2001:
  https://api.worldbank.org/v2/ (indicator codes are cache filenames).
  WDI data are retrospective revisions of 2001 observations, not a reconstruction
  of precisely what was known on 1 January 2001.
- Military personnel observations use the WDI series `MS.MIL.TOTL.P1`, sourced
  by WDI to IISS, *The Military Balance*. `MS.MIL.TOTL.P1.json` archives the
  2001 API response (release 2026-11-11; SHA-256
  `414455fa979fe1d58c2e3ed9469e3a94bf9779b4f2e4cea75a13128652080e8c`). Run
  `.venv/Scripts/python.exe utils/generate_military_personnel_wdi_2001.py` to
  regenerate `military_personnel_wdi_2001.tsv`, the 163 non-null exact ISO3
  matches to `countries_mil.tsv`. This tool writes only the separate ledger and
  raises an error if a WDI value differs from the current game table.
- CIA World Factbook 2001, public-domain US government content, archived at
  https://www.gutenberg.org/ebooks/27638 . Its edition contains estimates and
  older measurements identified in the original text. The provenance table
  separates the game's 2001 scenario year from each estimate year reported in
  the Factbook. Climate text and numeric estimates fill available fields before
  exact-year WDI observations override them.
- `factbook_land_metric_supplement_2001.tsv` also includes Kosovo's 41.7% forest
  estimate from the CIA World Factbook 2018, which explicitly labels it a 2001
  estimate. It fills the blank Kosovo forest field only. The game Serbia area
  includes Kosovo, so this scoped estimate does not create a separate Serbian
  forest total or area split. See `factbook_land_metric_supplement_2001.md` for
  the source and boundary note.
- World Bank WDI `SI.POV.NAHC` contributes exact 2001 national poverty-line
  headcount ratios only where the CIA Factbook has no estimate: Cabo Verde
  (56.8%), Timor-Leste (36.3%), and Uzbekistan (27.5%). The API response is
  cached as `SI.POV.NAHC.json`; source and observation year are retained in
  `provenance.tsv`. These are country-specific national-line estimates and
  should not be compared across countries. Metadata:
  https://databank.worldbank.org/metadataglossary/world-development-indicators/series/SI.POV.NAHC
- `climate_context_supplemental_2001.tsv` fills five absent descriptions while
  keeping source date and territorial scope explicit. Kosovo uses the 2007
  UNMIK core document, which cites the European Commission and World Bank's
  1999 reconstruction report; Serbia and Montenegro use the 2001 CIA Factbook
  climate description for the Federal Republic of Yugoslavia as a territory
  proxy; South Sudan uses only the Factbook's statement that southern Sudan was
  tropical before independence; East Timor uses the direct territorial climate
  description in a 2000 UN report. Their scenario reference year is 2001, but
  none is labeled as a 2001 weather observation. The rows retain the source
  document year, scope, notes, and link; the UI tooltip distinguishes proxies
  from direct country entries.
- UNDP Human Development Report 2025, retrospective observations for 2001:
  https://hdr.undp.org/data-center/documentation-and-downloads .
  `undp_hdr2025.csv` preserves the official complete time series in its original
  Windows-1252 encoding; its JSON manifest records the URL and SHA-256.
  The importer selects only 2001 HDI, life expectancy, expected and mean years of
  schooling, and gross national income per capita (2021 PPP international dollars).
  Available national HDI observations initialize `countries_dem.human_dev`.
  The world table uses UNDP's `ZZK.WORLD` aggregate (HDI 0.657), rather than an
  arithmetic average of national indices. The UI labels it as the historical
  2001 baseline; it does not pretend to recompute world HDI during gameplay.
- `hdi_backfills_2001.tsv` resolves the 29 country rows without an HDR 2025
  national 2001 score. Sixteen use HDI values published by UNDP for 2001 in
  HDR 2003; those values use the older literacy/enrolment/GDP formula and are
  explicitly distinguished from the HDR 2025 series. Seven scores are
  transparent estimates using the HDR 2025 formula and documented component
  substitutions or modeling. Four are regional, national-report, or territory
  proxies with their source periods identified. Antarctica and Vatican City
  have no comparable score; `countries_dem.human_dev` receives a neutral 0.50
  simulation fallback while the Country Information panel shows the HDI as
  unavailable. These estimates and proxies are not claimed as UNDP-published
  observations, and their status/method/source columns are copied into
  `countries_historical.tsv` for UI display and auditing.
- CIA Factbook poverty-line estimates are available for 96 game countries. The
  importer preserves each estimate's reported year, including cases where the
  source gives no year. Three additional exact-year WDI records fill only
  previously absent values; other countries remain unavailable.

`provenance.tsv` identifies the selected source, 2001 scenario year, reported
observation year when supplied, source document/edition year, territorial scope,
and source note for every imported field.
For HDI backfills, it retains the original source and distinguishes measured,
estimated, proxied, and simulation-only fallback values.
The generated `countries_historical.tsv` also carries the selected source
record for each numeric historical metric in
`historical_metric_provenance_json`. New-game History seeding reads that
field together with each metric's `_available` flag, so a measured zero stays
distinct from an unavailable value. The minute-zero History baseline keeps the
original scenario and observation years and tags estimates, proxies, derived
values, imputed land-use values, and bounded inferences separately.
Water area can be derived as WDI surface area minus land area; this is inland
water, not territorial seas. National historical geometry remains distinct from
the sum of regions currently controlled by a player.

Unavailable observations stay blank with an explicit availability flag. The flag
is required because the loader normalizes numeric nulls to zero. Neither a missing
observation nor an unimplemented simulation mechanic should be presented as zero.

National parks are not equivalent to all protected areas. Other land is not
equivalent to unusable land. National climate descriptions are not regional biomes.
Those distinctions must be preserved when adding the remaining geography inputs.

The former `Unusable land` UI slot now displays `Other land (2001)` using the
FAOSTAT Land Use series: `Other land` divided by `Land area`, both in 1,000 ha.
It is a residual land-use category rather than a judgment about whether land can
be used. Each country's FAOSTAT quality flag is retained in the historical
country table and provenance; the October 2026 archive marks all 193 matched
country values as imputed by a receiving agency (`I`), which the UI tooltip
shows. `faostat_land_use_2026.zip` is the archived 2026 bulk vintage and
`faostat_land_use_2026.json` records its checksum and 2001 selection method.

`factbook_land_metric_supplement_2001.tsv` preserves four land inputs from the
CIA World Factbook 2001 edition: Monaco arable land, Vatican City arable and
forest/woodland land, and Taiwan land area. The edition does not state the
observation year for these fields. The importer therefore keeps the source
edition year as 2001 and leaves `observation_year` null; tooltips must not
describe them as measured in 2001. Taiwan's land value completes the same CIA
area tuple already used for its total and water values.

The Country Information land tab uses the UNSD Environmental Indicators table at
`https://unstats.un.org/unsd/environment/TerrestrialProtectedAreas.htm`, last
updated in September 2010, for its reported 2000 proportion. This is nationally
designated terrestrial protected-area extent as a share of total country surface,
including inland waters; it includes categories beyond national parks. The source
also notes that some sites have no designation year and that unchanged reports
may carry prior values forward. The UI therefore labels the figure `Protected
areas (2000)` and never presents it as a 2001 national-parks-only measurement.
`unsd_terrestrial_protected_areas_2010.tsv` stores the mapped source rows used
for the game countries; its JSON manifest records the source page hash and the
observation and publication years. Country field provenance remains in
`provenance.tsv` and availability flags in `countries_historical.tsv`.

`national_park_terrestrial_2001_evidence.tsv` keeps the park-only measure in a
separate field. It records Kosovo's 390 km² Sharr National Park, Taiwan's
3,076.59 km² 2001 terrestrial national-park total (excluding Kenting's marine
area), zero 2001 park area for Maldives and São Tomé and Príncipe, and a
bounded zero inference for Nauru based on its 1996 conservation strategy and
later report of no gazetted protected areas. Antarctica is not applicable; five
other rows remain explicitly unavailable. The importer loads the five
supported or inferred values into `countries_historical.tsv`.
When the broad UNSD share is absent, the Country Information land slot labels
and displays the park-only 2001 value; it does not mix that value into the
broader protected-area field. The Maldives Ministry's 2024 register supports a
derived zero for its 2000 terrestrial protected-area share because all listed
pre-2000 designations are marine and its first listed terrestrial site is from
2004. That derived value fills the broad field with a specific source/method
tooltip and is not described as a direct UNSD observation. The ledger's
Markdown companion explains the sources, denominator, and why other later or
incompatible values remain unavailable.

`modules/base/data/regions/regions_pop.tsv` is generated by
`utils/import_historical_region_population.py`. The importer uses WorldPop's
Global1 2000-2020 1km population and age-sex rasters for observation year 2001.
It sums the 0, 1-4, 5-9, and 10-14 age bands for `pop_14`; sums the 65-69,
70-74, 75-79, and 80+ bands for `pop_65`; and derives `pop_15_64` from the
total-population raster minus those two groups. The WorldPop products are
retrospective modeled estimates, not measurements available to decision-makers
in 2001.

WorldPop cell centers are projected to the equirectangular `regions.png` mask
and assigned to the map region color. Because the 1km grid and the game map's
region boundaries do not align exactly, mapped regional counts are scaled
proportionally to the source-country raster total. The per-region correction
factor, coverage-cell count, chosen source, and status are recorded in
`regional_population_provenance.tsv`; `worldpop_regional_raster_sources.tsv`
stores each downloaded source URL, byte count, and SHA-256 digest. The importer
keeps raw GeoTIFFs in the ignored `.cache/worldpop/2001/` directory and reuses
them on later runs. They are not checked into the game data bundle.
`regional_population_legacy_baseline.tsv` preserves the pre-import regional
cohorts so regions without trustworthy source coverage remain stable across
repeat imports. If less than 20% of a source-country raster total maps to its
candidate game regions (a correction factor greater than 5x), the importer
records the raster evidence but does not use it to overwrite regional values.
`regional_population_overrides.tsv` records published territory-level totals
that are more specific than the available raster estimates. Coral Sea Islands
uses the official 2001 territory count. Agalega uses its latest located census
count from 2000 as the scenario baseline; its unavailable island age profile is
apportioned using Mauritius's raster-covered 2001 age shares. Maldives regions
use the official 2000 island/atoll and Malé counts carried into the 2001
scenario; age cohorts use the national 2000 census age distribution because
atoll-specific age counts are unavailable. Each override keeps its observation
year, source URL, status, and allocation method in the regional provenance
table. Estimated age splits are not presented as census counts.
Kiribati's Gilbert and Line/Phoenix totals are interpolated between official
2000 and 2005 census group totals; age cohorts use the published 2000 national
age shares. Marshall Islands' 2001 national projection and age groups are
allocated to Ralik and Ratak using their 1999 census population shares.
Territory- and chain-level age splits are modelled because source tables do not
publish those cohorts at the same geography.

Malta's 16 listed localities use the National Statistics Office's estimated total
population at 31 December 2001 (Table 6B). The publication has national, but not
locality-specific, age groups, so locality cohorts are allocated from its 2001
total-population age counts using largest-remainder rounding; these splits are
modeled, not locality census counts. The source's Isla locality is mapped to the
OpenPower region Senglea. Bonaire, Saba, and Sint Eustatius use the Netherlands
Antilles 2001 census totals and age groups in Table DE.6, cross-checked against
the island totals in Table G.1. Anguilla's Island Harbour and Sandy Ground totals
are taken from the 2001 district census table; their 0-14 and 15-64 counts come
from census Tables 8.3 and 8.10, and 65+ is the residual. See the corresponding
source URLs and per-row methods in `regional_population_overrides.tsv`.

Macquarie Island is a separate subantarctic station region, not one of the two
Antarctic map regions assigned the no-resident zero assumption. The Australian
Antarctic Program's 2001 station-leader article names the Macquarie Island
leader and reports 15–20 wintering people across Australia's four isolated
outposts. The regional override uses the rounded midpoint of that range (18)
as a modeled Macquarie station-presence estimate. The source does not publish
an exact Macquarie-only 2001 count or age breakdown, so the value is not a
census observation and all 18 are assigned to working age as an explicit
cohort model. The override's provenance row links the article and records this
method.

The data is licensed under CC BY 4.0. The 1km population-count product is DOI
10.5258/SOTON/WP00670, and the age-sex product is DOI 10.5258/SOTON/WP00654.
The 1km estimate is spatially coarser than many OpenPower regions. Regions with
no valid source cell or insufficient map overlap require a territory-specific
source or a clearly labeled model. No region should silently inherit an old
baseline without source-year and method provenance. Antarctica's two regions
are set to an explicitly identified zero-population assumption because the
source has no resident-population raster there; transient station staff are
excluded from those two values.

The World Bank terrestrial protected-area indicator `ER.LND.PTLD.ZS` is sourced
from Protected Planet/WDPA, but its published WDI reference period is 2013–2025,
and its definition combines national parks with several other protection classes.
It cannot fill a national-parks-only 2001 field. WDPA releases also backfill older
designation years as countries report sites, so filtering a current release by
designation year would not reconstruct the 2001 database snapshot. See the
[indicator metadata](https://databank.worldbank.org/metadataglossary/millennium-development-goals/series/ER.LND.PTLD.ZS),
Protected Planet's [release and use restrictions](https://www.protectedplanet.net/en/news-and-stories/why-do-we-have-different-versions-of-the-wdpa),
and its [WDPA reporting lag explanation](https://www.protectedplanet.net/en/news-and-stories/the-lag-effect-in-the-world-database-on-protected-areas).

The two conflicting PSE/PSX population-extension records for West Bank and Gaza
were resolved to the PSE records matching the master regions' owners. Each region
now has one population record; alternate-owner rows cannot share the same primary key.

Regional biomes are assigned from the RESOLVE Ecoregions 2017 classification
using each OpenPower map region center. The layer is a useful spatial baseline
for the 2001 scenario, not a 2001 ecological survey. Its compressed source
snapshot, CC BY 4.0 attribution, and checksum are recorded in
`resolve_ecoregions_2017_manifest.json`; the region-keyed assignments are in
`modules/base/data/regions/regions_biomes.tsv`. The service response is
generalized at 0.0025 degrees to match the map's regional scale; invalid
geometries are repaired for point lookup, with the repair count and generalization
recorded in the manifest.

Remaining implementation scope: exact 2001 national-parks-only data,
per-characteristic research, model assets, multiplayer, and localization gaps
described in the audit.

Domestic production now supports normal and fast modes. The fast mode's 50% cash
premium and 25% factory-work reduction are explicit gameplay tuning, not sourced
historical statistics. UI quotes and authoritative orders use the same policy;
foreign production remains subject to seller terms.

Diplomatic pressure is derived from the live military state rather than supplied
as a historical observation. A treaty's pressure share is its sponsors' fielded
equipment value divided by world fielded equipment value. National pressure is
the union of sponsors of unanswered proposals or suspended memberships, divided
by the target's fielded military value plus one, capped at one. Supporting a
proposal does not accept it for anyone. Supporters can withdraw; acceptance or
removal of the proposal clears the corresponding national pressure. Pressure
causes 15 relationship points of annual decay, prorated by game days.

Reference evidence: `.codex/Client/Source/sp2_treaties_detailed_window.cpp`,
`GTreatyDetailsWindow::FillPressure`; `.codex/sp2-hdm-full-reference/Server/Source/sp2_world_behavior.cpp`,
`GWorldBehavior::IterateLossRelationsFromPressure`; and
`.codex/sp2-server-reference/sp2_constants.h`, `c_fRelationLossAnnualyFromPressure`.

The resource market now accepts optional per-resource `desired_trade_usd` and
`meet_consumption` policy fields through `ActionUpdateResourcePolicy`. Positive
targets request exports; negative targets request imports. Targets use the same
annual USD valuation as domestic production. Automatic consumption coverage is
the default. Discretionary exports cannot exceed physical supply; discretionary
imports of storable goods can build reserves, while nonstorable imports are
limited to consumption gaps. Bilateral treaty restrictions remain authoritative.

`countries.global_resource_tax_modifier` is added to sector resource tax and
the effective rate is bounded to 100%. Its 2% default preserves the existing
OpenPower market surcharge; this is a gameplay default, not a claimed historical
2001 national tax observation. Both NumPy and Polars clearing paths use these
policies and preserve goods withheld from export or imported for reserves.

The Resources UI edits these fields through client-owned drafts, keeps a shared
national tax draft across resource selections, and waits for snapshots before
clearing pending commands. Rejections retain the draft for retry. Trade targets
are entered in millions of USD per year; tax input uses percentage points.
Market-only changes preserve unedited fractional sector tax rates exactly.
The `resource-market-policy-editing.json` UI journey verifies native input,
navigation between resources, and the resulting authoritative command payload.

Additional region-level population sources correct several preserved legacy
baselines. INSEE's 1 January 2001 estimates supply totals and broad age bands
for Guadeloupe, Martinique, and French Guiana; Réunion uses its official 2001
estimate with 1999 census age shares. Mayotte and Oued Ed-Dahab totals are
linear interpolations between their surrounding census observations. Gibraltar
and four Cook Islands entries use published 2001 census totals and age groups.
Palau's Hatohobei and Sonsorol totals use its 2000 state census counts carried
to the 2001 scenario; age groups are modeled from national census shares.
Tokelau uses the later UN territory paper's 1,518 census count, while other UN
summaries report 1,537; the selected observation and discrepancy are recorded
in provenance. Svalbard uses the official 2001 aggregate, with modeled age
shares. U.S. Minor Outlying Islands use Census 2000 resident counts carried to
the scenario; Johnston's age split is a staffing assumption and source dashes
for the other islands are treated as zero. Bouvet Island's zero is an explicit
uninhabited-territory assumption, not a 2001 census observation. Every added
record retains the source URL, observation year, status, and age-allocation
method in `regional_population_overrides.tsv` and
`regional_population_provenance.tsv`.

The remaining 18 uncovered region baselines were replaced with source-backed
territory totals or explicit station-population models. The CIA World Factbook
2001 estimate is used for Western Sahara and Vatican City. Kashmir uses the
official 2001 Kashmir-region census total; Northern Cyprus uses a linear
interpolation between the official 1996 and 2006 censuses. Akrotiri and
Dhekelia combine the Republic of Cyprus's 2001 civilian counts with the UK
Parliament's approximate base-personnel total, allocated by published base
garrison shares. Guantanamo Bay uses a contemporaneous 2001 estimate; British
Indian Ocean Territory, Malpelo, Isla de Aves, the South Georgia stations, the
TAAF research stations, and the Scattered Islands use sourced or modeled
station staffing. Paracel and Spratly garrisons carry forward the nearest
published 2000 estimate. Rose Atoll is an explicitly sourced zero-resident
assumption. When a source lacks the game's age bands, the file records the
cohort allocation method; modeled cohorts are not described as census counts.
For the remote military and research stations, the population represents
people assigned to the station in the scenario, not an indigenous or family
settlement.

Further legacy-region corrections use the exact 2002 census counts for
Razkrižje (Slovenia) and Saint Louis (Seychelles), carried unchanged as the
nearest scenario-year observations. Razkrižje's five-year age groups are
published directly; Saint Louis age cohorts are modeled from Seychelles'
national 2002 age counts because the district table does not publish them.
Tuvalu uses the Central Statistics Division's June 2001 estimate of 10,223,
as quoted in the Asian Development Bank's 2002 review; its age cohorts are
modeled by scaling the 2002 census age distribution to that estimate. The
source-year difference and the allocation method remain explicit in provenance.

The 2001 CIA World Factbook describes Ashmore and Cartier Islands as having no
indigenous inhabitants and seasonal caretakers, and Heard and Clipperton as
uninhabited. These regions use zero permanent-resident assumptions; temporary
caretakers, researchers, and visitors are excluded. A secondary summary of the
2001 New Zealand census lists three residents for the Kermadec Islands. Stats NZ
confirms the islands were covered by that census but aggregates them with the
North Island or areas outside local authorities in published tables. The
reported total is retained with its secondary-source caveat; because no
island-level age table was found, all three residents are modeled as working-age
DOC-station staff. This replaces an implausible legacy total of 174,000 without
presenting an unsupported zero as a census result.

`country_languages_factbook_2001.tsv` preserves the 2001 CIA World Factbook
`Languages` text for 193 of the 199 game countries; five territories have no
separate 2001 entry and Antarctica's entry has no language field. Its manifest
records source and extracted-file checksums. The Internal Laws language Details
view displays this text as historical context alongside, but separate from,
the game's numeric language-share estimates. The Factbook does not provide a
uniform and mutually exclusive language-share measure, so its descriptions are
not converted into percentages or used to overwrite `country_languages.toml`.

`countries_unit_research_2001.tsv` provides twelve modeled characteristic
factors for each of 199 countries. The generator reproduces the existing
bootstrap scaling formula from historical HDI inputs and OpenPower's research
budget scenario setting. These low-confidence factors are gameplay design
inputs, not measured national defense research, deployed weapon capability, or
historical technology ceilings. Research progress and funding remain branch-
level live simulation values; they are echoed in characteristic slots with
tooltips explaining that no historical per-characteristic series exists.
Regenerate the table after changing its input data with
`python utils/generate_unit_research_baseline_2001.py`.
