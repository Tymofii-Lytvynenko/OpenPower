# 2001 Military Equipment Evidence Candidates

This ledger preserves six source reviews for specific naval platform counts. All six are now imported into `military_equipment_inventory_supplement_2001.tsv` and applied to the runtime scenario inventory. Five have 2001 source observations; the UK carrier count is a clearly labeled moderate-confidence 2000 near-year estimate. Each record remains limited to the named role, fleet definition, and observation period.

| Country | Role | Candidate count | Observation date | Scope |
|---|---|---:|---|---|
| United States | Aircraft carriers | 12 | 2001-09-30 | Active ship inventory; readiness and deployment are not implied. |
| United States | Ballistic missile submarines (SSBNs) | 18 | 2001-09-30 | Active SSBN inventory; deployed patrol count and readiness are not implied. |
| France | Aircraft carriers | 1 | 2001-11-22 | In-service fleet inventory; the contemporaneous report estimates 60% availability. |
| France | Ballistic missile submarines (SSBNs) | 4 | 2001-07 | The report says four were in operation; only three were in the operational cycle. |
| United Kingdom | Ballistic missile submarines (SSBNs) | 4 | 2001-11 | Four-boat Vanguard fleet; the inventory count does not mean four boats were on patrol. |
| United Kingdom | Aircraft carriers | 3 | 2000-03-17 | Official near-year fleet roster; two were normally available for tasking. |

## Evidence and scope

The U.S. Naval History and Heritage Command's [ship force levels table](https://www.history.navy.mil/research/histories/ship-histories/us-ship-force-levels.html) gives the 2001-09-30 active force counts directly: 12 carriers and 18 SSBNs. The FY 2001 Department of the Navy [budget submission](https://www.secnav.navy.mil/fmc/fmb/Documents/01pres/ops/OMN_BOOK.PDF) corroborates the counts, stating that the force structure provides for 12 aircraft carriers and 18 ballistic missile submarines, and that USS John F. Kennedy transferred from reserve to active force during FY 2001. The candidate values describe fleet inventory, not ships on deployment or ships meeting an unstated readiness threshold.

The French Senate's [2002 budget opinion for the Navy](https://www.senat.fr/rap/a01-090-8/a01-090-86.html), deposited 2001-11-22, explicitly describes Charles de Gaulle as the sole carrier in service. It records the ship's admission to active service on 2001-05-18 and estimates its availability at 60%. The candidate is therefore one in-service platform on the report date, not one continuously available carrier. The count is taken from the report's explicit fleet-wide statement rather than inferred by adding or subtracting ships mentioned in separate partial sources.

The [July 2001 French Nuclear Forces assessment](https://journals.sagepub.com/doi/10.2968/057004016) reports four French SSBNs in operation. It distinguishes the four-boat fleet inventory from the three boats maintained in the operational cycle and the smaller number on patrol.

The [November/December 2001 British Nuclear Forces assessment](https://doi.org/10.1080/00963402.2001.11460521) documents the four-boat Vanguard SSBN force. HMS Vengeance began its first deterrent patrol in February 2001. The [UK House of Commons 2000 carrier statement](https://hansard.parliament.uk/Commons/2000-03-17/debates/3844514d-479d-47c0-b80a-2ef527a97a8d/WrittenAnswers) names Invincible, Illustrious, and Ark Royal as the three carriers and says two were normally available. This older roster is retained as a near-year scenario estimate, not an exact 2001 observation.

## Integration status

All six rows in [military_equipment_candidates_2001.tsv](military_equipment_candidates_2001.tsv) have `imported_to_maintained_supplement` status. The focused tests compare them with the maintained supplement and verify that the inventory importer applies only the ledger-listed cells.
