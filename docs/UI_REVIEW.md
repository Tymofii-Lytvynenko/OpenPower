# OpenPower UI Review: Internal Laws and Bilateral Trade

**Review date:** 2026-10-09

**Scope:** Internal Laws, language and religion profiles, and bilateral trade.
**Review mode:** Initial UI review followed by a check of implemented changes.

## Implemented changes

The following updates were completed after the initial review:

- Internal Laws displays language and religion groups, shares, legal statuses, row-level source details, and explanations of statuses and the unavailable Other category.
- Added actual laws, party summaries, and migration-policy summaries with links to their respective panels. Removed inactive demonstration sections.
- Trade has separate offer-building and history pages, a conditions summary, two columns on wide windows, and a vertical layout on narrow windows. A counteroffer starts with the original terms and swaps the sides.
- The initial Laws and Trade windows are separated on wide screens. Several large windows can overlap on small screens; players can move or close them. Automatic window layout is not available.
- Added stable IDs and UI-agent scenarios: 14 identity steps and 25 trade steps. Both scenarios were reported as passing at 1280×720 and 800×600 without rendering or geometry errors; an additional render ran at 1920×1080.
- A full-client run checked the map, HUD, Politics, Internal Laws, Economy, and Trade. It reported no system errors, and the Ukraine profile loaded language and religion data. The integration screenshot was a generated local artifact and is not retained in the repository.

A missing production data-loading step was also fixed: DataLoader now calls the shared profile loader. A live run contained 1,596 distribution rows and 1,596 groups. A separate regression test covers the loading path.

Remaining work includes UI localization, verified national sources and years for each profile, automatic layout for multiple windows, and additional integration checks.

## Review method

The initial review rendered the OpenPower internal-laws and trade surfaces at 1280×720; Trade was also checked at 1920×1080. Temporary demonstration rows were used to populate both language and religion tables. These rows were not statistics for Ukraine or another country. Trade was reviewed in a standard test world without creating or sending offers. Later synthetic UI scenarios used a recording client and checked submitted actions; they did not execute server-side deal settlement.

The initial surface renders reported no rendering errors. Trade geometry passed, while identity diagnostics reported clipping in the Languages and Religions tabs. Later UI-agent scenarios clicked both tabs and reported no geometry errors at 1280×720 or 800×600; the initial warning did not recur. These checks do not establish that every label is readable.

The rendering harness shows an isolated panel on a black background. By itself it does not show interaction with the map, HUD, or neighboring panels. A later full-client run checked the map, HUD, Politics, Internal Laws, Economy, and Trade, confirming integration of these surfaces. Overlap after a country change and on narrow windows has not been assessed systematically.

## Summary

OpenPower provides entry points through Politics → Internal Laws and Economy → Trade. Trade supports cash, regions, technology, and an offer/response cycle. The identity screen shows language and religion shares and allows their legal statuses to be changed. Party and migration policy remain in separate panels, with summaries and direct links in Internal Laws.

| Priority | Current finding | Follow-up |
|---|---|---|
| High | The full client integration check confirmed the map, HUD, Politics, Internal Laws, Economy, and Trade work together, but did not measure map overlap after a country change or on a narrow window. | Repeat the integration review after changing countries and at a small window size. Save screenshots if the map or controls become inaccessible. |
| Medium | Each row shows its origin and notes that it is a built-in estimate without a recorded source year. Verified national sources and methods are not yet available for these estimates. | Add verified sources, definitions, and years when established. Keep unknown years unknown and do not present estimates as census results. |
| Medium | Tooltips explain legal statuses and why the aggregate Other group cannot be edited. | Ask players whether this behavior is clear; change it only if the interaction review finds confusion. |
| Medium | Trade shows both sides next to each other in a wide window and stacks them on a narrow one. It includes a conditions summary and offer/history pages. The synthetic scenario checks submissions and responses, but not simulation settlement. | In a live scenario, check whether the deadline, response reasons, and expiration outcome are clear. |
| Low | Headings and buttons are currently in English. | If OpenPower adds a multilingual UI, localize group names, statuses, tooltips, and messages consistently. |

## Surface details

### Language, religion, and internal laws

- Languages and religions have separate tabs with group shares and status selectors for editable groups.
- The default panel size is 450×560. Its table shows Group, Share, Status, and row-level source details, including an unknown source year.
- Check in the live client that the message about missing laws does not confuse players when an identity profile is loaded.

### Bilateral trade

- Trade opens from the Economy panel.
- Players build separate YOU GIVE and YOU REQUEST sides, set a deadline, and review incoming, outgoing, pending, and completed offers.
- Incoming offers can be accepted, rejected, or countered; outgoing offers can be withdrawn.
- The default window size is 760×720. It shows cash, available regions and technologies, a conditions summary, and a separate history page.
- The rendering harness checked 1280×720, 800×600, and 1920×1080 without geometry errors.
- Trade's actual composition over the map, panel switching in the running game, and the complete cycle with a live AI country were outside the visual harness review.

## Next checks

1. Review the integrated screen at a narrow window size and after changing countries; check that the map and panels remain accessible.
2. Check whether players can find group statuses, share sources, and party/migration controls without searching across multiple windows.
3. Complete a bilateral trade in a test world with the live simulation. Check whether the parties can tell who transfers each asset, why the offer was accepted or rejected, and what happens at expiration. Existing synthetic UI scenarios cover submissions and responses at 1280×720 and 800×600, but not server settlement.

## Internal references

- Internal Laws: src/client/ui/panels/politics/internal_laws_panel.py
- Trade: src/client/ui/panels/trade_panel.py
- Politics: src/client/ui/panels/politics_panel.py
- Economy: src/client/ui/panels/economy_panel.py
- Panel registry: src/client/ui/layouts/game_panel_registry.py
- UI testing guide: docs/UI_TESTING.md

This document records the initial review and the reported status of subsequent changes. The initial review itself did not change the UI, gameplay, or game data.
