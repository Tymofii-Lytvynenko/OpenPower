# 2001 world treaties and conflict records

## Epoch and scope

The inclusion date is the game epoch, **2001-01-01**. This audit covers only
`modules/base/data/world/countries_treaties.toml` and
`modules/base/data/world/countries_wars.toml`. It preserves the existing TOML
collection format and country-tag fields. The tab-separated
`world_conflicts_treaties_2001.tsv` ledger records one or more source links for
each addition, correction, removal, and newly identified war record.

Treaty party lists record historical legal participation. They do not by
themselves assert that the engine should dispatch military support. The two
consultative treaty types added here are not defined as gameplay treaty types;
the existing treaty contract retains the type string, while
`treaty_definition()` returns no effects for it.

## Treaty changes

- **Rio Treaty:** corrected its parties against the U.S. State Department
  *Treaties in Force* roster dated 2001-01-01. The roster has 22 parties,
  including Cuba, Haiti and Nicaragua; Trinidad and Tobago is not on that
  roster. The source reflects party status, not political participation in
  every treaty measure.
- **ANZUS:** retained all three treaty parties and added a note that the United
  States suspended its obligations as between itself and New Zealand in 1986.
  The 2001 U.S. roster still lists Australia, New Zealand and the United States
  as parties.
- **Manila Pact:** added the Southeast Asia Collective Defense Treaty as a
  seven-party record: Australia, France, New Zealand, the Philippines,
  Thailand, the United Kingdom and the United States. The 2001 U.S. roster
  distinguishes the treaty, still in force, from the SEATO organization, which
  had dissolved in 1977. Pakistan is excluded because its one-year denunciation
  notice took effect in 1973. The terms preserve the treaty's constitutional
  process and U.S. understanding; this entry does not create automatic
  OpenPower defense effects.
- **Five Power Defence Arrangements:** added Australia, Malaysia, New Zealand,
  Singapore and the United Kingdom. The arrangement requires consultation over
  an attack or threat against Malaysia or Singapore. Its data type is
  consultative and non-effecting in the simulation.
- Removed the generic `us_thailand_major_ally` row. The U.S. Major Non-NATO Ally
  designation came in December 2003, after this scenario date. The Manila Pact
  entry retains Thailand's actual treaty participation and notes the 1962
  Rusk-Thanat commitment without asserting a separate bilateral treaty.

## Conflict changes

- The war table now has stable IDs, names, and explicit `active` statuses for
  its six retained records. Stable IDs allow actions that refer to a war to
  target the source record rather than a UI-generated fallback identifier.
- In the Second Congo War entry, removed Chad (`TCD`): the UN reported that
  Chad withdrew on 1999-05-26. Retained the DRC, Angola, Namibia and Zimbabwe
  on one side and Rwanda, Uganda and Burundi on the other. An International
  Crisis Group report dated 2000-12-20 estimated Burundian forces remained
  deployed in the DRC, which establishes presence at the epoch. Burundi
  described the operation as self-defense and denied belligerent status; the
  ledger marks its country-level status as contested. This is a participation
  proxy, not a legal finding that Burundi was at war with the DRC.
- Removed the USA/UK-Iraq row. The 1991 Gulf War was over before the epoch and
  the 2003 Iraq invasion had not begun. This does not make a separate claim
  about no-fly-zone enforcement or occasional air strikes.
- Removed the Eritrea-Ethiopia row. The parties signed a cessation agreement
  in June 2000 and Article 1 of the 12 December 2000 Algiers Peace Agreement
  required them to permanently terminate military hostilities. UNMEE's
  monitoring of the ceasefire and border settlement continued, but that does
  not make the interstate war an active-war record at the epoch.

## Retained-record caveats

The existing country-level war schema cannot represent armed organizations,
peacekeepers, external support, or legal belligerent status independently.
Accordingly, these retained rows should not be read as a complete participant
database or as proof that every country tag was directly fighting another
state on 2001-01-01.

- `second_intifada` uses `PSE` as a proxy for Palestinian actors; it does not
  assert that a sovereign Palestinian state declared war.
- `kashmir_conflict` is a coarse territorial-conflict proxy. The Indian 2000
  human-rights report describes insurgent violence, and India had announced a
  ceasefire beginning in November 2000. The `IND`/`PAK` sides do not establish
  a direct India-Pakistan interstate war at the epoch.
- `sierra_leone_civil_war` and `mano_river_border_conflict` include external
  country tags while the central armed actors were non-state groups such as
  the RUF. In the Sierra Leone row, peacekeeping or training contributions are
  not equivalent to belligerency. The UN reported January 2001 fighting in the
  Sierra Leone-Guinea border area and incursions into Liberia; that regional
  proxy conflict was not a formal Guinea-Liberia declaration of war.
- `sudan_uganda_proxy_conflict` remains labeled as a proxy conflict, not a
  state-to-state war. Sudan and Uganda had agreed in December 1999 to restore
  diplomatic relations and promote peace; the available source evidence does
  not establish direct hostilities on the exact epoch.

Two additional internal conflicts are documented but not imported as runtime
war rows. UN General Assembly resolution A/RES/55/174, adopted 19 December
2000, describes ongoing hostilities between Afghan parties, including the
Taliban and United Front. A written statement received by the UN on 12 January
2001 describes Colombia's internal armed conflict involving the State, FARC,
ELN, and paramilitary groups including AUC. The current war schema requires
both sides to be lists of country tags and has no non-state actor identifiers.
Mapping these factions to invented countries, putting a country tag on both
sides, or substituting foreign supporters would misstate the actors. Their
omission is a schema limit, not a claim that the conflicts were inactive.

## Validation

`tests/test_world_2001_treaties_wars.py` verifies the epoch, exact corrected
party sets, no-effect treaty types, removed war claims, stable war IDs, and
per-record provenance. `tests/test_data_loader_mod_layering.py` checks the
updated six-row war table through the existing world TOML loader.

The ledger deliberately records publication and observation dates separately
from the scenario date. In particular, a report published after 1 January may
corroborate activity during the same January but is labeled as later evidence,
not contemporaneous proof of activity on the exact day.
