# 2001 Military Inventory Data

countries_mil.tsv contains one starting record for each of the 199 country and territory entries in the game roster. It keeps personnel separate from equipment inventory so a tank count is never treated as a troop count.

## Roster fields

- military_count is active military personnel.
- The 20 military_*_quantity_2001 fields store starting quantities by role. Infantry quantity is personnel; quantities for vehicles, aircraft, ships, submarines, and missiles are item counts.
- unit_designs.starting_quantity_2001 copies the relevant starting quantity into each country's design for that role.
- unit_designs.capabilities_json stores each country's role characteristics, including baseline hit points, gun and missile fire rates, missile rearm delay, movement, and combat fields used by OpenPower.
- units.strength remains the personnel assigned to a deployed group; units.equipment_quantity is the number of items represented by that group. This lets combat losses, deployments, and equipment sales update both measures without conflating them.

The role IDs and their starting quantity fields are:

| Military role | Role ID | Starting quantity field |
| --- | --- | --- |
| Infantry | infantry | military_infantry_quantity_2001 |
| Infantry vehicles | infantry_vehicles | military_infantry_vehicles_quantity_2001 |
| Air defense | air_defense | military_air_defense_quantity_2001 |
| Mobile launchers | mobile_launchers | military_mobile_launchers_quantity_2001 |
| Tanks | tanks | military_tanks_quantity_2001 |
| Artillery | artillery | military_artillery_quantity_2001 |
| Attack helicopters | attack_helicopters | military_attack_helicopters_quantity_2001 |
| Transport helicopters | transport_helicopters | military_transport_helicopters_quantity_2001 |
| Anti-submarine helicopters | anti_submarine_helicopters | military_anti_submarine_helicopters_quantity_2001 |
| Fighter aircraft | fighters | military_fighters_quantity_2001 |
| Attack aircraft | attack_aircraft | military_attack_aircraft_quantity_2001 |
| Bombers | bombers | military_bombers_quantity_2001 |
| Patrol craft | patrol_craft | military_patrol_craft_quantity_2001 |
| Corvettes | corvettes | military_corvettes_quantity_2001 |
| Frigates | frigates | military_frigates_quantity_2001 |
| Destroyers | destroyers | military_destroyers_quantity_2001 |
| Attack submarines | attack_submarines | military_attack_submarines_quantity_2001 |
| Ballistic missile submarines | ballistic_missile_submarines | military_ballistic_missile_submarines_quantity_2001 |
| Aircraft carriers | aircraft_carriers | military_aircraft_carriers_quantity_2001 |
| Ballistic missiles | strategic_missiles | military_strategic_missiles_quantity_2001 |

Role baselines include hit points, firing rates, and missile rearm delay. The anti-submarine helicopter baseline is an approximation because the source material does not provide a separate stat block for that role. Speed, protection, sensors, weapon ranges, precision, payload, damage, stealth, and countermeasures are additional scenario characteristics. Country development and research inputs scale these characteristics without changing role identity or its baseline values.

## Historical basis and estimates

For game-country IDs with a matching published 2001 observation, military_count follows the World Bank World Development Indicators series MS.MIL.TOTL.P1, sourced to IISS, The Military Balance. An audit against the live World Bank API on 15 November 2026 matched 163 of the 199 roster records to non-null 2001 observations, with all 163 values exactly equal to countries_mil.tsv. This series counts active-duty armed forces and qualifying paramilitary personnel; it excludes reservists and may contain IISS estimates where country data is uncertain.

The exact 163 WDI matches are listed by ISO3 code in `modules/base/data/sources/2001/military_personnel_wdi_2001.tsv`. The raw API response is archived as `MS.MIL.TOTL.P1.json` (source release 2026-11-11; SHA-256 `414455fa979fe1d58c2e3ed9469e3a94bf9779b4f2e4cea75a13128652080e8c`). Rebuild the separate ledger with `python utils/generate_military_personnel_wdi_2001.py`; the generator verifies every source value against `countries_mil.tsv` and fails on a mismatch without modifying the game table.

- [World Bank indicator methodology](https://databank.worldbank.org/metadataglossary/world-development-indicators/series/MS.MIL.TOTL.P1)
- [World Bank API: 2001 observations](https://api.worldbank.org/v2/country/all/indicator/MS.MIL.TOTL.P1?date=2001&format=json&per_page=300)
- [IISS, The Military Balance 2001–2002](https://www.routledge.com/The-Military-Balance-2001-2002/IISS/p/book/9780198509790)

Equipment counts are more limited. The Bahrain, Kuwait, Oman, Qatar, Saudi Arabia, United Arab Emirates, Iran, and Iraq profiles use contemporary IISS-derived regional tables as anchors. Other major-power profiles are hand-tuned scenario estimates. For the remaining roster entries, the generator uses a deterministic manpower and development model, with country-specific geographic and force-structure rules. A few irregular or demilitarized forces have explicit light-force overrides to prevent the generic model from inventing large conventional fleets.

- [Washington Institute: 2001 GCC military inventory, sourced to IISS](https://www.washingtoninstitute.org/policy-analysis/gcc-militaries-desert-storm-assessment)
- [Congressional Research Service: IISS-derived Iran, Iraq, and Gulf inventory table](https://www.policyarchive.org/download/1553)

These country inventories are playable 2001 scenario estimates, not a complete official census of every country's stored or operational equipment. Figures from different source tables may use different definitions, and some type splits, such as infantry vehicles versus other armored vehicles, are modeled to fit the role catalog. The generator is utils/generate_military_inventory_2001.py.

A focused source ledger now covers 27 equipment-role counts across 12 countries in `modules/base/data/sources/2001/military_equipment_inventory_supplement_2001.tsv`. Nine naval counts cover Russia, China, India, the United States, France, and the United Kingdom: Russia's 17 operational ballistic-missile submarines assessed in May 2001, China's zero PLAN aircraft carriers reported by CRS in November 2001, India's one carrier in service stated by the Defence Minister in March 2001, the U.S. Navy's 12 active carriers and 18 active SSBNs on 2001-09-30, France's one in-service carrier and four reported-in-operation SSBNs in 2001, and the UK's four-boat Vanguard SSBN force in 2001. The UK carrier count of three comes from a 2000 fleet roster and is explicitly a moderate-confidence near-year scenario estimate; two were normally available for tasking. The French carrier report estimates 60% availability. The U.S. inventory counts do not imply deployment or readiness. For India, the parliamentary answer says the proposed Russian carrier still required repair and modernization before induction; the proposed indigenous ship was not yet in service. The RUS value replaces the previous scenario estimate of 15.

The other 18 records add 2001 GCC table counts for Bahrain, Kuwait, Oman, Qatar, Saudi Arabia, and the United Arab Emirates: tanks and artillery for all six, plus each state's broader armored-vehicle total mapped to `infantry_vehicles` as a moderate-confidence role proxy. The source is the Washington Institute's 2001 state-by-state table, which attributes its numbers to IISS's 2000/01 *The Military Balance*. Those six vehicle totals are not exact IFV/APC counts. Across all 27 entries, the supported role IDs are `tanks`, `artillery`, `infantry_vehicles`, `aircraft_carriers`, and `ballistic_missile_submarines`. Source definitions, scope limits, confidence, and field mapping are recorded per row; see the [equipment supplement note](../sources/2001/military_equipment_inventory_supplement_2001.md). None of these rows validates other equipment fields for those countries or the rest of the roster.

Reproduce the ledger values by running `python utils/import_military_equipment_supplement_2001.py` after inventory generation. The importer validates the country, role field, scenario year, nonnegative integer, and source attribution before changing only the ledger-listed cells. Run it with `--check` to verify that all 27 table values match the ledger without writing the table.

The 36 roster records without a matching non-null World Bank 2001 personnel observation now have 25 row-level records in `modules/base/data/sources/2001/military_personnel_supplemental_2001.tsv`, leaving 11 entries without a supported personnel reference. The supplemental ledger includes 17 observations dated 2001, five dated 2002, two dated 2000, and one dated 1999. The non-2001 records remain explicitly marked as nearest-year observations rather than exact 2001 counts. Combined with the 163 exact WDI matches, 188 of 199 roster rows have a row-level source observation; some records have a narrower scope or a non-2001 observation year, as noted in the ledger.

The second source review added Comoros from an OAU expert mission assessment in early 2002: its National Army for Development (AND) is reported at about 1,070 personnel, comprising the Comorian Defence Force, National Gendarmerie, VIP-security officers, and medical staff. The report gives the National Police separately at about 400. The 1,070 is therefore an approximate 2002 AND count, not a 2001 observation. Timor-Leste's 2001 UN report supports 941 regular Defence Force personnel by adding 594 soldiers who had graduated basic training and 347 additional recruited cadets in training; this includes trainees and does not mean all 941 were operationally deployable. The 1,500-person reserve was a planned strength and is excluded. São Tomé and Príncipe's 1,000 is the nearest non-null WDI/IISS observation found, for 1999; it is two years before the scenario and is not treated as a 2001 observation or an interpolated estimate. These details and exact source references are recorded in the ledger.

The 11 active-personnel gaps are AFG, ATA, KOS, MCO, MNE, PSE, SLB, SMR, SOM, SSD, and PRI. Sources reviewed for Afghanistan report factional forces or a broad range of Taliban combatants, not a single national active-force count. Antarctica is not a sovereign military roster and the Antarctic Treaty permits military personnel for peaceful scientific/logistical support without establishing an Antarctic force. Kosovo's KPC sources describe a civilian emergency service and document that the late-2001 establishment list was not validated. Monaco's 2002 statistics give 112 Carabiniers but do not supply a complete count for all military-status public-force corps, so that partial unit strength is not entered as a country total. Montenegro was a constituent republic of the Federal Republic of Yugoslavia; counts of Yugoslav forces stationed there and of armed police/reservists are not a distinct Montenegrin armed force. Palestine sources report legal ceilings or estimates of security-services payrolls, with evidence of ghost personnel, rather than a verified active military count. Solomon Islands had no regular military in the 2001 Factbook, but the listed police and reconnaissance/paramilitary services have no complete cited personnel count. San Marino sources identify two small active military units but provide no headcount. Somalia's interim-government sources describe an army under formation and recruits registered for training, without an accurate active count. South Sudan was not a sovereign country in 2001 and the SPLA cannot be treated as a national armed force. Puerto Rico has no separate sovereign armed force; National Guard personnel are part of the United States forces. These 11 game-table values have no comparable historical source and must not be described as observations. A separate, gameplay-only estimate ledger provides low/very-low-confidence population-rate estimates for nine IDs, including PRI only as a territorial allocation proxy; ATA is not applicable and SSD remains unavailable. The [estimate method and data table](../sources/2001/military_personnel_gameplay_estimates_2001.md) make that model reproducible. These estimates do not replace or enter the factual active-personnel sources or `countries_mil.tsv`.

The runtime extension `countries_military_personnel_gameplay_estimates_2001.tsv` exposes those nine values in separate, namespaced columns and keeps a unique row per country for the standard country-table join. Rebuild it with `python utils/generate_military_personnel_gameplay_estimates_2001.py`; `--check` verifies that it matches the source ledger. The Unit List shows a read-only `2001 GAMEPLAY ESTIMATE` reference for the player's own country when available. Foreign-country views retain their aggregate intelligence-confidence display and expose the historical estimate in that value's tooltip. The tooltip states that the estimate is not a historical count and is separate from current `military_count` and deployed unit strength. The PRI note identifies its value as a territorial force-allocation proxy, not Puerto Rico armed-forces strength.

The sources do not all use the same scope. Some report regular armed forces and explicitly exclude police; WDI instead includes active paramilitary forces when their organization and equipment indicate a military role, while excluding reservists. The ledger records the scope and method for each supplemental row. A zero in a regular-force source does not establish a WDI-equivalent count of every security service. Taiwan's 400,000 is an official retrospective count from the Ministry of National Defense. Côte d'Ivoire's 14,000 is the 2001 COW NMC value transcribed from IISS, The Military Balance 2002-2003. Swaziland's 2,700 comes from the contemporary Child Soldiers Global Report 2001 and replaces the modeled 3,000; COW NMC v7 separately records 27,000 from IISS 2002-2003, a tenfold discrepancy that remains unresolved. The ledgers state the evidence and confidence so these figures are not mistaken for a fully harmonized census.

To reproduce the supported personnel values, run `python utils/import_military_personnel_supplement_2001.py`, then regenerate the affected model allocations with `python utils/generate_military_inventory_2001.py --country CIV SWZ TLS TON VUT`. The importer changes only ledger-listed `military_count` cells. The focused generation recalculates only those five country rows so their modeled infantry and support allocation stays within the sourced active-personnel total; these equipment-role quantities remain scenario estimates, not source-backed facts.

## Strategic weapons

The land-based ballistic-missile field and ballistic-missile submarine counts seed the strategic weapon inventory. Submarine-launched missile totals use 16 missiles per boat where no explicit scenario override exists. The strategic_missiles field does not represent every nuclear warhead or tactical missile; it models strategic ballistic weapons.
