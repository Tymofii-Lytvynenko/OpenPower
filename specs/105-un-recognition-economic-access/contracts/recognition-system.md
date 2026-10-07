# Recognition System Contracts

## Player intent and authority

`ActionCastRecognitionVote` carries the inherited player identity plus `case_id`, `country_tag`, and `vote` (`yes`, `no`, or `abstain`). The action is intent, not authority. The authoritative recognition system requires a pending case, a currently eligible captured voter, a valid vote, an unexpired deadline, and player control of that country. A valid replacement updates the existing case/country vote; invalid or late actions do not change the case.

## Case opening and resolution

1. On a relevant claim/region change, inspect completed annexation claims in stable ID order.
2. Open one case only for an `annexed` claim whose claimant currently owns and controls the region and for which no case already exists.
3. Capture the sorted eligible roster from `countries.un_member`, excluding claimant and former owner. Set the configured deadline, defaulting to 30 game days.
4. AI countries use the same vote path as players. The policy considers diplomatic relations, active wars, and configured alliance/common-market/economic-partnership/economic-union interests.
5. Resolve only when game time reaches the deadline. Passage requires a strict majority of the captured roster; otherwise reject. Persist aggregate totals and the final reason.
6. On passage, persist `recognized` for yes voters and `not_recognized` for every other captured voter. Rejection grants no recognized status.
7. If owner or controller no longer matches the claimant, withdraw pending/passed case and any recognized statuses associated with the claim.

The lifecycle publishes typed open, vote-changed, resolved, and withdrawn events plus user-visible diplomacy/news updates. Events are consequences of authoritative state changes, not client commands.

## Regional economic access

- A domestic participant is allowed only if it is both current owner and controller.
- For foreign trade, preserve the explicit `source_region_id` from `regional_production` into the bilateral flow and evaluate access before market reconciliation.
- A disputed region requires a passed current case and a non-withdrawn `recognized` status for the importing country. Existing treaty allocation priority does not bypass recognition.
- If no regional-output record exists, do not apportion national production or attach an invented region to a flow. Country-level aid, credit, tax, and budget records without region provenance remain country-level; any future region-sourced flow must carry provenance and use this gate.
- Regions without an active recognition claim retain existing regional-trade behavior, subject to current owner/controller validation.

## Persistence and presentation

All authoritative cases, votes, and statuses live in registered state tables and therefore use existing schema migration, save/load, snapshot, and IPC mechanisms. The presenter exposes case status, claimant, former owner, deadline, aggregate votes, the selected country's vote/status, and region-level recognition counts. Client panels remain projections and submit only shared actions.
