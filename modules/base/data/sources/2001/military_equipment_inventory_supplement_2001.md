# 2001 Military Equipment Supplement

This source note describes the 27 entries in `military_equipment_inventory_supplement_2001.tsv`. The source ledger supplements the playable inventory with narrowly scoped records; it does not certify every equipment value in the game.

## Gulf Cooperation Council inventories

The Washington Institute published its state-by-state table on 2001-02-22. Table II labels the later column `2001` and says its figures come from IISS's 2000/01 edition of *The Military Balance*. The table provides a directly comparable count of tanks, artillery, and armored vehicles for each GCC state:

| Country ID | Tanks | Artillery | Source armored vehicles | Game field for vehicle total |
| --- | ---: | ---: | ---: | --- |
| BHR | 106 | 98 | 365 | `military_infantry_vehicles_quantity_2001` |
| KWT | 385 | 59 | 495 | `military_infantry_vehicles_quantity_2001` |
| OMN | 117 | 115 | 183 | `military_infantry_vehicles_quantity_2001` |
| QAT | 44 | 40 | 212 | `military_infantry_vehicles_quantity_2001` |
| SAU | 1,055 | 448 | 2,870 | `military_infantry_vehicles_quantity_2001` |
| ARE | 331 | 270 | 1,053 | `military_infantry_vehicles_quantity_2001` |

The tank and artillery rows preserve the source categories. The source's broader `armored vehicles` totals are mapped to the game's `infantry_vehicles` role as moderate-confidence proxies; the published category does not establish that every item is an infantry fighting vehicle or armored personnel carrier. The source also cautions that inventory figures do not show battlefield performance or readiness, and some equipment may not be operational.

Source: [Washington Institute, “The GCC Militaries since Desert Storm: An Assessment,” Table II, published 2001-02-22](https://www.washingtoninstitute.org/policy-analysis/gcc-militaries-desert-storm-assessment). The paper says its 2001 column is drawn from IISS, *The Military Balance 2000/01*.

## Naval counts

The other nine entries record named carrier or submarine counts for RUS, CHN, IND, USA, FRA, and GBR. Their source dates, observation scope, confidence, and limitations are recorded per row in the TSV. The six U.S., French, and British additions also have a separate review at `military_equipment_candidates_2001.md`. These are inventory, in-service, or operational-assessment counts as each source describes them; they do not assert continuous readiness or deployment.

## Coverage and reproduction

The 27 entries cover five game roles: `tanks`, `artillery`, `infantry_vehicles`, `aircraft_carriers`, and `ballistic_missile_submarines`. There are no source-backed role counts here for other roles, other countries, or unlisted fields within these 12 countries. The source ledger is applied by `python utils/import_military_equipment_supplement_2001.py`; `--check` verifies the 27 mapped country-field values without writing the inventory.
