# Supplemental election and political context for the 2001 scenario

This table is separate from the CIA World Factbook 2001 extractor. It adds
source-backed names for political/electoral entities that provide historical
context for the 2001 scenario. Each record keeps the actual year of its source
event; the supplement is not a claim that every election took place in 2001.
The records are loaded into `country_party_roster_supplemental_2001` and
displayed in a separately labelled section of the Country Information roster
dialog. The table includes election-result entities and source-bounded political
movement context; each row retains its source field and territory scope.

| Game ID | Records | Source scope |
| --- | ---: | --- |
| KOS | 14 | Kosovo Assembly entities that won seats in the 17 November 2001 election; the OSCE reports 26 contestants. |
| MNE | 16 | Electoral-list labels in the OSCE/ODIHR final-results table for 22 April 2001. Labels can refer to parties or coalitions. |
| PSE | 2 | Exact Fatah and Independent Fatah categories in the Palestinian Central Elections Commission's 20 January 1996 Legislative Council results. These are earlier electoral context, not a complete 2001 roster. |
| SRB | 4 | The four seat-winning lists named by Serbia's National Assembly for the 23 December 2000 election. |
| SSD | 1 | CIA Factbook 2001 lists the Sudan People's Liberation Army as a political pressure group for Sudan, with Dr. John Garang; this is southern-Sudan territory context, not a separate country party roster or election result. |
| TLS | 12 | East Timor parties that won national seats in the 30 August 2001 Constituent Assembly election; 16 parties registered. |

## Sources

- [OSCE Mission in Kosovo, final results of the 2001 Assembly election](https://omik.osce.org/kosovo/54021) names the 14 entities that won seats and distinguishes the 26 total contestants.
- [OSCE/ODIHR Election Observation Mission Report for Montenegro, 22 April 2001](https://www.osce.org/files/f/documents/a/2/15168.pdf) gives the final results table with all 16 electoral-list labels on page 17. The report also explains party and coalition context.
- [UNTAET Independent Electoral Commission, final East Timor Constituent Assembly results, 6 September 2001](https://peacekeeping.un.org/sites/default/files/past/etimor/DB/db060901.htm) lists 12 seat-winning parties and notes the election held on 30 August.
- [Serbia's National Assembly, history after the Second World War](https://www.parlament.gov.rs/national-assembly/history/after-second-world-war.534.html) names the four lists that won seats in the 23 December 2000 Serbian Assembly election. The event predates the 2001 scenario and is recorded with source year 2000.
- [Palestinian Central Elections Commission, The 1996 Presidential and Legislative Elections](https://www.elections.ps/portals/0/pdf/resultselection1996.pdf) reports the exact Fatah and Independent Fatah Legislative Council categories. Only those two named faction categories are carried here; the source's broader independent/group categories are not treated as party names. The records retain source year 1996 and are not presented as a 2001 election or a complete 2001 roster.
- [CIA World Factbook 2001, Sudan](https://www.gutenberg.org/cache/epub/27638/pg27638.txt) lists the Sudan People's Liberation Army and Dr. John Garang under political pressure groups and leaders. Its country entry describes Sudan as a whole in 2001, so the SSD row is explicitly limited to southern-territory political context.

Every record stores its source name, reference, URL, and scope note. The source
most source rows do not provide a party-leader field; a leader is shown only
when the source explicitly names one. Election vote shares and seats are not loaded as gameplay support,
eligibility, or ruling-party status. The source-bounded lists do not claim to be
complete party censuses for each territory. The `source_year` column is the
actual year of the record, which may predate 2001.

The CIA-only extract and its checksum manifest remain unchanged. This importer
rebuilds only the supplemental runtime table and manifest:

```powershell
.venv\Scripts\python.exe utils/import_supplemental_party_roster_2001.py
```

Antarctica has no national electoral party roster, and South Sudan was not a
separate country in 2001. Its single supplemental record is a Sudan-wide
Factbook reference to the SPLA, with a scope note that prevents it being read as
a separate South Sudan party list. The West Bank Factbook entry omits the field; the two
PSE rows therefore show only the specifically named Fatah categories from the
1996 official results, without inferring a broader 2001 roster. Serbia's four
rows come from its own 2000 Assembly election, not from allocating records in
the combined Yugoslavia Factbook entry. Montenegro and Kosovo records likewise
remain sourced from their own election materials.
