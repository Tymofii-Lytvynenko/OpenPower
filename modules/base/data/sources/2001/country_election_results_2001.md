# Historical election-results ledger

This source ledger records four election events already referenced by the supplemental party roster. Each row is a result for the actual event date and geography in its primary source. The rows are historical outcomes; vote shares do not represent gameplay party support, and no row assigns ruling status or election eligibility.

| Event | Rows | Result coverage | Aggregate result retained |
| --- | ---: | --- | --- |
| Kosovo Assembly election, 17 November 2001 | 26 | All political entities in the certified result table | 788,303 votes; 120 seats |
| Montenegro Assembly election, 22 April 2001 | 16 | All party and coalition labels in the final results table | 363,404 list votes; 72 general and 5 special-station seats |
| East Timor Constituent Assembly election, 30 August 2001 | 12 | Parties with national-list seats | 75 national-list seats; party vote shares, no per-party raw counts |
| Serbian National Assembly election, 23 December 2000 | 8 | All electoral lists in the final result report | 3,660,849 votes; 250 mandates |

## Sources and scope

- [Kosovo Central Election Commission certified results, hosted by OSCE Mission in Kosovo](https://omik.osce.org/sites/default/files/f/documents/6/4/20466.pdf) supplies the 26 political-entity vote totals, source-reported percentages, and Assembly seats. The OSCE [final-results notice](https://omik.osce.org/kosovo/54021) dates the election to 17 November 2001 and the announcement to 26 November 2001. The supplemental roster contains only the 14 seat-winning entities; this result ledger preserves all 26.
- [OSCE/ODIHR Election Observation Mission Report for Montenegro](https://www.osce.org/files/f/documents/a/2/15168.pdf), page 18, reports the final results released on 5 May for the 22 April 2001 election. It distinguishes 72 general seats from five seats allocated through special polling stations. The ledger retains the source-printed percentages and records blank seat-allocation cells as zero mandates. The report says 366,152 people voted; list vote totals sum to 363,404 because votes cast and list votes are not identical. Its threshold calculation includes invalid votes and votes from special stations.
- [UNTAET Independent Electoral Commission final results](https://peacekeeping.un.org/sites/default/files/past/etimor/DB/db060901.htm) were announced on 6 September 2001 for the 30 August election. The twelve percentages and mandates refer to the national-list ballot and its 75 proportional seats. The 13 district seats were elected separately and are not attributed to these party-list rows. The announcement reports percentages but does not provide each party's raw vote count, so the vote field is left empty.
- [Republic Election Commission of Serbia final report](https://arhiva.rik.parlament.gov.rs/doc/arhiva/poslanici/2000/2.%20izvestaj%20o%20ukupnim%20rezultatima%202000.pdf) reports eight lists' votes and mandates. It covers polling held on 23 December 2000 and 10 January 2001, and was adopted on 12 January 2001. The ledger records the first as the primary election date and the second in `additional_election_date`. The source reports counts, not percentages, so vote shares are left empty. The supplemental roster contains only the four lists that won seats; this ledger includes all eight.

`country_election_results_2001.tsv` is the reviewed source ledger. The importer writes its rows to the separate `country_election_results` world table and creates a checksum manifest:

```powershell
.venv\Scripts\python.exe utils/import_country_election_results_2001.py
```

The runtime table is available as static historical result data. It does not feed political-party support, current election simulation, eligibility, or ruling-party status. PSE's 1996 results are intentionally omitted from this 2001/2000 election set.
