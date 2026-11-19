# 2001 Factbook language source extract

`country_languages_factbook_2001.tsv` preserves the CIA World Factbook 2001
`Languages` field for each game country with a separate source entry. The
Factbook says its information generally reflects what was available on
1 January 2001, while noting selected content can be updated periodically.

The extract has 199 rows: 193 reported language fields, one country entry with
no language field, and five game territories that did not have a separate
country entry in the 2001 source. The latter are Kosovo, Montenegro, Serbia,
South Sudan, and East Timor. No parent-country language estimate is assigned
to those territories.

Only line wrapping was normalized. The source wording remains intact, including
its explicit percentages and caveats. The Factbook does not provide a uniform
measure of mutually exclusive language shares: many entries name official or
minority languages without percentages, and some note bilingualism. The extract
therefore does not convert those descriptions into population percentages and
does not replace the existing `country_languages.toml` profiles.

The TSV and its JSON manifest record the source URL, source checksum, row-level
coverage status, and extraction method. The source is the [Project Gutenberg
edition of the 2001 CIA World Factbook](https://www.gutenberg.org/ebooks/27638).

The existing Internal Laws language Details view receives this source context.
It continues to identify population shares as OpenPower gameplay estimates, and
keeps the share's source year as unrecorded. The Factbook wording is a historical
note only; it is not used to calculate or label a population share.
