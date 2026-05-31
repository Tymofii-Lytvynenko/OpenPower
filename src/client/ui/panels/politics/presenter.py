from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from src.client.ui.panels.shared.panel_data import (
    as_percent,
    as_ratio,
    format_members_count,
    get_country_row,
    normalize_side,
    resolve_country_name,
    resolve_region_name,
    safe_float,
    safe_int,
    safe_text,
)


@dataclass(frozen=True, slots=True)
class PoliticsSummaryViewModel:
    government_type: str
    ideology_balance: float
    approval_pct: float
    stability_pct: float
    corruption_pct: float
    capital_name: str
    next_election: str
    martial_law: bool
    election_risk_pct: float
    active_treaties: int
    pending_treaties: int


class PoliticsPresenter:
    def build_summary(self, state, country_tag: str) -> PoliticsSummaryViewModel:
        country_row = get_country_row(state, country_tag)
        government_row = self._government_row(state, country_tag)

        capital_id = safe_int(government_row.get("capital_region_id"))
        active_treaties = len(self.active_treaties_for_country(state, country_tag))
        pending_treaties = len(self.pending_treaties_for_country(state, country_tag))
        return PoliticsSummaryViewModel(
            government_type=safe_text(government_row.get("government_type"), "Transitional republic"),
            ideology_balance=as_ratio(government_row.get("ideology_balance"), 0.5),
            approval_pct=as_percent(country_row.get("gvt_approval"), 50.0),
            stability_pct=as_percent(country_row.get("gvt_stability"), 50.0),
            corruption_pct=as_percent(country_row.get("gvt_corruption"), 40.0),
            capital_name=resolve_region_name(state, capital_id),
            next_election=safe_text(government_row.get("next_election"), "Unscheduled"),
            martial_law=bool(government_row.get("martial_law", False)),
            election_risk_pct=as_percent(government_row.get("election_risk"), 0.0),
            active_treaties=active_treaties,
            pending_treaties=pending_treaties,
        )

    def laws_for_country(self, state, country_tag: str) -> list[dict]:
        laws = state.tables.get("country_laws")
        if laws is None or laws.is_empty() or "country_id" not in laws.columns:
            return []

        return (
            laws.filter(pl.col("country_id") == country_tag)
            .sort(["group_name", "title"])
            .to_dicts()
        )

    def active_treaties_for_country(self, state, country_tag: str) -> list[dict]:
        treaties = state.tables.get("countries_treaties")
        if treaties is None or treaties.is_empty():
            return []

        rows: list[dict] = []
        for row in treaties.to_dicts():
            members = normalize_side(row.get("members"))
            side_a = normalize_side(row.get("side_a"))
            side_b = normalize_side(row.get("side_b"))
            all_members = members or tuple(sorted(set(side_a) | set(side_b)))
            if country_tag not in all_members:
                continue

            relation_score = self.average_relation_score(state, country_tag, [tag for tag in all_members if tag != country_tag])
            rows.append(
                {
                    "id": safe_text(row.get("id"), ""),
                    "name": safe_text(row.get("name"), safe_text(row.get("id"), "Treaty")),
                    "type": safe_text(row.get("type"), "agreement"),
                    "members": all_members,
                    "members_count": format_members_count(all_members),
                    "relation_score": relation_score,
                }
            )

        return sorted(rows, key=lambda item: (item["type"], item["name"]))

    def pending_treaties_for_country(self, state, country_tag: str) -> list[dict]:
        pending = state.tables.get("pending_treaties")
        if pending is None or pending.is_empty():
            return []

        rows = pending.filter(
            (pl.col("source_country_id") == country_tag) | (pl.col("target_country_id") == country_tag)
        )
        return rows.sort("created_at", descending=True).to_dicts()

    def preferred_treaty_partners(self, state, country_tag: str, limit: int = 12) -> list[dict]:
        relations = state.tables.get("countries_relations")
        if relations is None or relations.is_empty():
            return []

        if not {"source", "target", "value"}.issubset(set(relations.columns)):
            return []

        rows = (
            relations.filter(pl.col("source") == country_tag)
            .sort("value", descending=True)
            .head(limit)
            .to_dicts()
        )
        return [
            {
                "country_tag": safe_text(row.get("target")),
                "country_name": resolve_country_name(state, safe_text(row.get("target"))),
                "relation_score": safe_float(row.get("value")),
            }
            for row in rows
        ]

    def average_relation_score(self, state, country_tag: str, peers: list[str]) -> float:
        relations = state.tables.get("countries_relations")
        if relations is None or relations.is_empty() or not peers:
            return 0.0

        if not {"source", "target", "value"}.issubset(set(relations.columns)):
            return 0.0

        filtered = relations.filter(
            (pl.col("source") == country_tag) & (pl.col("target").is_in(peers))
        )
        if filtered.is_empty():
            return 0.0
        return float(filtered["value"].mean() or 0.0)

    def _government_row(self, state, country_tag: str) -> dict:
        governments = state.tables.get("country_governments")
        if governments is None or governments.is_empty() or "country_id" not in governments.columns:
            return {}

        rows = governments.filter(pl.col("country_id") == country_tag)
        if rows.is_empty():
            return {}
        return rows.to_dicts()[0]
