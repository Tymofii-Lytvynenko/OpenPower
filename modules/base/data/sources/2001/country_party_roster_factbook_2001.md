# CIA World Factbook 2001 party roster

The importer extracts named entries from the CIA World Factbook 2001 field
`Political parties and leaders` and loads them as the read-only
`country_party_roster_2001` world table. The separate
`country_party_roster_coverage_2001` table records source availability for all
199 game country identifiers. The source is the [Project Gutenberg
edition of the 2001 CIA World Factbook](https://www.gutenberg.org/ebooks/27638);
the bundled text and manifest record the downloaded file's checksum.

The Factbook says information generally available as of 1 January 2001 was
used, while selected content may have later updates. It does not give a
field-specific observation or estimate year. The table records the source
edition year and field on every row; it does not claim an exact estimate date.
The source field does not provide comparable party vote shares, support
shares, or a ruling-party indicator, so none are included or inferred.

Before this backfill, the base data had no party roster file. The political
initializer created one generic `Incumbent` row with 100% gameplay support for
each of the 199 countries. Those rows are simulation fallbacks, not historical
party records. The Factbook rows remain in a separate table so they do not gain
invented support, eligibility, or ruling-party values.

## Coverage

The game has 199 country identifiers. The Factbook field maps to 192 of them,
with 1,385 individually named party, bloc, or coalition entries. The remaining
seven country identifiers are recorded explicitly in
`country_party_roster_coverage_2001.tsv`:

| Country ID | Status | Evidence |
| --- | --- | --- |
| ATA | `party_field_not_reported` | The Factbook has an Antarctica entry without this field. |
| PSE | `party_field_not_reported` | The Factbook has a West Bank entry without this field. |
| KOS | `no_separate_country_entry` | No separate 2001 Kosovo entry. |
| MNE | `no_separate_country_entry` | No separate 2001 Montenegro entry. |
| SRB | `no_separate_country_entry` | The 2001 edition identifies Serbia and Montenegro as Yugoslavia; no Serbia-specific roster is assigned. |
| SSD | `no_separate_country_entry` | No separate 2001 South Sudan entry. |
| TLS | `no_separate_country_entry` | No separate 2001 East Timor entry. |

Separate historical electoral records provide 14 Kosovo seat-winning entities,
16 Montenegro electoral-list labels, and 12 East Timor parties that won national
seats in 2001; four Serbian seat-winning lists from the 2000 election; and two
named Palestinian Legislative Council outcome categories from 1996. They are
stored in `country_party_roster_supplemental_2001`, shown as alternate-source
records with their actual source years, and do not change this CIA-only coverage
ledger or extract. ATA and SSD still have no supplemental named records; PSE's
two 1996 categories are not a complete 2001 roster. Their source limits are
described in
[`country_party_roster_supplemental_2001.md`](country_party_roster_supplemental_2001.md).

The edition has 231 party-field entries across all 267 country and location
entries. It also names non-game locations and entries that cannot be mapped to
the game's identifiers. These are not copied into game countries. No party
list is borrowed from a predecessor, successor, or neighboring territory.

## Record handling

- Source line wraps are collapsed, but names and leader wording are preserved.
- Semicolons split records only outside parentheses and leader brackets.
- Narrative `note` text remains in `source_notes`; generic descriptions such as
  “several other groups” do not become fabricated party records.
- `leader_status` distinguishes leaders named in brackets, bracketed `leader
  NA`, and entries that list no leader.
- `party_id` is a stable OpenPower slug derived from the name. It is not a
  source-provided identifier.
- The historical roster is separate from `political_parties`, which is the
  simulation table and requires gameplay attributes the Factbook does not
  supply. The historical rows are not assigned support, eligibility, or ruling
  status by this import.

Regenerate the extract, coverage ledger, runtime TOML, and checksum manifest
from the bundled source with:

```powershell
.venv\Scripts\python.exe utils/import_factbook_party_roster_2001.py
```
