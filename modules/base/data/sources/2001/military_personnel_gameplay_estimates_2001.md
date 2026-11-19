# 2001 Gameplay-Only Military Personnel Estimates

This separate ledger provides low or very-low confidence values for nine game scenarios whose active-personnel counts do not have comparable source observations. These are gameplay estimates, not historical counts. Every row sets `historical_observation=no`, `factual_active_personnel_eligible=no`, and `import_target=none`; none changes the World Bank or supplemental factual ledgers or `countries_mil.tsv`.

## Reproducible method

For each estimate, sum the 2001 `pop_14`, `pop_15_64`, and `pop_65` values in `regional_population_provenance.tsv` for that country's `owner`. This gives the WorldPop 2001 country or territory population used by the game map. For each listed peer, divide its exact 2001 World Bank WDI `MS.MIL.TOTL.P1` active-personnel value by its WorldPop population and multiply by 1,000. The regional service-rate baseline is the median of those peer rates. Multiply the target population by that median and divide by 1,000, then round to the nearest person using half-up rounding.

The underlying personnel observations come from the [World Bank API series MS.MIL.TOTL.P1 for 2001](https://api.worldbank.org/v2/country/all/indicator/MS.MIL.TOTL.P1?date=2001&format=json&per_page=300), archived with its release and checksum in `military_personnel_wdi_2001.tsv`. The population inputs are derived from the [WorldPop 2001 1 km population raster](https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/2001/) and its [population](https://doi.org/10.5258/SOTON/WP00670) and [age-sex estimates](https://doi.org/10.5258/SOTON/WP00654), recorded per game region in `regional_population_provenance.tsv`.

| Peer group | Peer ISO3 codes | Estimate IDs | Notes |
| --- | --- | --- | --- |
| South/Central Asia | BGD, IND, IRN, PAK, TJK, TKM, UZB | AFG | Broad regional prior across South and Central Asian countries. |
| Balkans | ALB, BIH, BGR, HRV, GRC, MKD, ROU, SVN | KOS, MNE | Kosovo and Montenegro do not have comparable separate national-force observations for 2001. |
| Western Europe | AUT, BEL, CHE, DEU, ESP, FRA, ITA, LUX, NLD | MCO, SMR | General European prior; it is not a microstate-specific rate. |
| Caribbean | ATG, BHS, BRB, BLZ, CUB, DOM, GUY, HTI, JAM, SUR, TTO | PRI | Territorial force allocation proxy only; it is not a Puerto Rico national military count or a count of U.S. forces stationed there. |
| Middle East | EGY, IRN, IRQ, ISR, JOR, LBN, SAU, SYR, TUR | PSE | Broad regional prior; it does not estimate verified Palestinian Authority strength. |
| Pacific islands | FJI, PNG | SLB | Only two peers have WDI personnel observations in the chosen small-island comparison set. |
| Horn/East Africa | DJI, ERI, ETH, KEN, RWA, SDN, TCD, TZA, UGA | SOM | Regional prior; it does not turn Somalia's recruitment registration pool into an active-force count. |

The exact population totals, peer rates, peer IDs, rounded estimates, data-use flags, and row-specific limitations are included in `military_personnel_gameplay_estimates_2001.tsv`. The focused test recomputes each total and median from the source ledgers so the calculations can be reproduced.

## Scope limits

The rate method is a gameplay prior, not a country-specific historical model. It inherits WDI's active-duty and qualifying-paramilitary definition, excludes reservists, and can include IISS estimates. Peer medians can be distorted by conscription, conflict, or country-specific force structures; this is why the estimate quality is low or very low. It must not be presented as an observation or merged into factual active-personnel series.

Antarctica (`ATA`) is not a sovereign military roster and has no scenario estimate. South Sudan (`SSD`) did not exist as a separate sovereign-force scope in 2001 and remains unavailable; the SPLA cannot be converted into a national count with a regional rate. Puerto Rico (`PRI`) is included only as a territorial gameplay allocation proxy and must not be interpreted or aggregated as an independent armed force.
