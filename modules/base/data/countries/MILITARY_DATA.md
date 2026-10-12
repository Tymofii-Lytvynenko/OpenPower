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

For countries with a published 2001 observation, military_count follows the World Bank World Development Indicators series MS.MIL.TOTL.P1, sourced to IISS, The Military Balance. The series reports 163 entries for 2001 and is an aggregate active-duty headcount rather than an equipment inventory.

- [World Bank indicator methodology](https://databank.worldbank.org/metadataglossary/world-development-indicators/series/MS.MIL.TOTL.P1)
- [World Bank API: 2001 observations](https://api.worldbank.org/v2/country/all/indicator/MS.MIL.TOTL.P1?date=2001&format=json&per_page=300)
- [IISS, The Military Balance 2001–2002](https://www.routledge.com/The-Military-Balance-2001-2002/IISS/p/book/9780198509790)

Equipment counts are more limited. The Bahrain, Kuwait, Oman, Qatar, Saudi Arabia, United Arab Emirates, Iran, and Iraq profiles use contemporary IISS-derived regional tables as anchors. Other major-power profiles are hand-tuned scenario estimates. For the remaining roster entries, the generator uses a deterministic manpower and development model, with country-specific geographic and force-structure rules. A few irregular or demilitarized forces have explicit light-force overrides to prevent the generic model from inventing large conventional fleets.

- [Washington Institute: 2001 GCC military inventory, sourced to IISS](https://www.washingtoninstitute.org/policy-analysis/gcc-militaries-desert-storm-assessment)
- [Congressional Research Service: IISS-derived Iran, Iraq, and Gulf inventory table](https://www.policyarchive.org/download/1553)

These country inventories are playable 2001 scenario estimates, not a complete official census of every country's stored or operational equipment. Figures from different source tables may use different definitions, and some type splits, such as infantry vehicles versus other armored vehicles, are modeled to fit the role catalog. The generator is utils/generate_military_inventory_2001.py.

## Strategic weapons

The land-based ballistic-missile field and ballistic-missile submarine counts seed the strategic weapon inventory. Submarine-launched missile totals use 16 missiles per boat where no explicit scenario override exists. The strategic_missiles field does not represent every nuclear warhead or tactical missile; it models strategic ballistic weapons.