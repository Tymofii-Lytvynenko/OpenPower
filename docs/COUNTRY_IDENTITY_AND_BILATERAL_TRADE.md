# Country Identity and Bilateral Trade

**Updated:** 2026-10-09

**Scope:** Single-player simulation and local UI. Multiplayer transport and synchronization were not changed.

## Country language and religion data

OpenPower stores language estimates in modules/base/data/countries/country_languages.toml and religion estimates in modules/base/data/countries/country_religions.toml. Each file contains profiles for 199 country codes, with 829 language labels and 767 religion labels in total. The loader drops records for countries absent from the active world, preserves group names, and normalizes each non-empty profile to 100 percent.

The files do not identify a census or observation year for each profile. The game therefore labels these rows as **built-in game estimates** and records year 0 (unknown), rather than assigning them a recent census year. The normalized profiles work with the current game rules, but they are not verified, comparable census series. Countries may use different definitions for native language, language spoken at home, language knowledge, religious belief, or affiliation with a religious organization. The UN describes these different definitions and recommends documenting each country's definition. UNECE also notes that these characteristics are sensitive, dynamic, and connected to the right to self-identification. See the [UN Statistical Division definitions](https://unstats.un.org/unsd/demographic/sconcerns/popchar/popcharmethods.htm), [UNECE 2030 census recommendations](https://w3.unece.org/recs2030census/webpage24.html), and [UN Demographic Yearbook census datasets](https://unstats.un.org/unsd/demographic-social/products/dyb/index.cshtml#censusdatasets), which publish language and religion tables when national data are available. The [2025 CIA World Factbook archive](https://www.cia.gov/the-world-factbook/about/archives/2025/countries/benin/factsheets/) is another dated country reference; its data have not been attributed to these profiles without a separate review of each one.

### Data quality and source work

- Each profile needs a source URL, publication or collection year, indicator definition, and a note about possible overlap between categories.
- If a source permits multiple answers for languages or religions, normalization to 100 percent does not establish mutually exclusive population shares. The model needs an explicit estimate or a separate schema for non-overlapping indicators.
- Prefer national statistical offices and censuses, followed by the UN Demographic Yearbook. Available years and topics differ by country; add a profile only when its definition and denominator are known.
- Some countries do not collect or publish religion data. Keep absent or withheld values unknown rather than treating them as zero.

### Simulation rules

Each identity row belongs to a country and a dimension (language or religion), and includes a name, share, legal status, source metadata, and last-change time. Players can assign a group one of four statuses: official, legal, restricted, or illegal. The aggregate Other category is displayed but cannot be assigned a status.

On each in-game day while the simulation is running, shares from restricted or illegal groups gradually move to the largest recognized group in the same dimension. Restricted groups shift at 0.5% per game year; illegal groups shift at 2% per year. The change is proportional to each group's current share. This simplified identity rule does not move people between regions or change the total population. Policy signals are averaged separately for language and religion, then affect civil rights and stability. At least one other non-zero group in each dimension must remain legally recognized.

## Bilateral trade

The system uses the diplomatic_trade_deals table and deterministic game actions. A package can include cash, regions, and a researched technology field. The proposing country transfers offered_assets and receives requested_assets; a counteroffer swaps the countries' roles and creates a linked record.

### Deal lifecycle

1. A country sends a package to another country. The server validates both sides and sets a deadline from 1 to 365 days, defaulting to 30.
2. The recipient can accept, reject, or counter. The proposer can withdraw the offer. A counteroffer closes the previous offer and stores a link between the records.
3. When an offer is accepted, the server rechecks player authority, war status, ownership, balances, occupation of regions, research levels, capitals, and each country's final region.
4. Only after all assets pass validation does the server transfer cash, change region ownership, move a capital when needed, and copy technology. The recipient gets the field's current level and unlocked items; the seller keeps its own research.
5. When the deadline passes, the next day event expires the offer. AI accepts a valid package when the estimated value received is at least 90% of the value requested. If an offer is too large, AI may construct a deterministic counteroffer from a smaller subset of the assets requested by the player; if it cannot construct one, it rejects the deal with an explanation.

Countries at war cannot trade through this system; peace deals handle wartime transfers. Resource imports and exports remain in the global resource market. Since regional GDP is unavailable, AI estimates a region's value as the country's GDP divided by its number of regions. Technology value depends on the recipient's GDP and newly unlocked research levels. These deterministic estimates are heuristics for AI responses.

## Implementation boundaries

The UI is available in the existing Trade and Internal Laws panels. It uses the current local game-action path; network messages, protocol, synchronization, and simultaneous actions by multiple players were not added.

## UI and implementation checks

Internal Laws displays both profiles, shares, statuses, source/year/notes, summaries of laws, parties, and migration policy. Party and migration controls are available through direct links. Trade has a bilateral offer builder, a conditions summary, separate history, and counteroffers prefilled from the original conditions. Country data and drafts stay separate when the selection changes.

The production DataLoader loads profiles through StaticAssetLoader.load_country_identity_distribution before state normalization. A full-client run contained 1,596 distributions and 1,596 groups; a previous omission of this path was fixed.

Twenty tests were reported as passing across tests/test_identity_bilateral_workflows.py and tests/test_data_loader_mod_layering.py. They cover both policy dimensions, country control, protection of Other, pause/day-to-day share changes, preservation of the 100% total, cash/region/technology transfers, rejection without partial transfer, counteroffers, withdrawals, expiration, AI responses, and module data overrides. The identity-policy.json (14 steps) and bilateral-trade.json (25 steps) UI scenarios were reported as passing at 1280×720 and 800×600. They check submitted actions; separate tests cover simulation outcomes.

This document describes current single-player rules. The profile values remain game estimates, and identity changes are not connected to physical population movement. Multiplayer behavior was not changed.
