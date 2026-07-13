"""Deterministic bilateral resource allocation under treaty constraints."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import polars as pl


TRADE_FLOW_SCHEMA = {
    "exporter_id": pl.Utf8,
    "importer_id": pl.Utf8,
    "game_resource_id": pl.Utf8,
    "trade_value_usd": pl.Float64,
}


class TreatyTradePolicy:
    """Allocates common-market transfers before the constrained global market."""

    CONSTRAINT_EFFECTS = {"common_market_priority", "resource_trade_embargo"}

    def has_constraints(self, effects: pl.DataFrame | None) -> bool:
        return bool(
            effects is not None
            and not effects.is_empty()
            and effects.filter(pl.col("effect").is_in(self.CONSTRAINT_EFFECTS)).height
        )

    def allocate(self, market: pl.DataFrame, effects: pl.DataFrame) -> pl.DataFrame:
        common_peers, embargoes = self._constraints(effects)
        flows: list[dict[str, Any]] = []
        for resource_id, resource_market in market.group_by("game_resource_id", maintain_order=True):
            resource = str(resource_id[0] if isinstance(resource_id, tuple) else resource_id)
            supplies = {
                self._tag(row["country_id"]): max(0.0, self._number(row.get("export_desired")))
                for row in resource_market.to_dicts()
            }
            demands = {
                self._tag(row["country_id"]): max(0.0, self._number(row.get("affordable_import")))
                for row in resource_market.to_dicts()
            }
            self._allocate_phase(flows, resource, supplies, demands, common_peers, embargoes, common_only=True)
            self._allocate_phase(flows, resource, supplies, demands, common_peers, embargoes, common_only=False)
        return pl.DataFrame(flows, schema=TRADE_FLOW_SCHEMA, strict=False) if flows else pl.DataFrame(schema=TRADE_FLOW_SCHEMA)

    def _allocate_phase(
        self,
        flows: list[dict[str, Any]],
        resource: str,
        supplies: dict[str, float],
        demands: dict[str, float],
        common_peers: dict[str, set[str]],
        embargoes: set[frozenset[str]],
        *,
        common_only: bool,
    ) -> None:
        for importer in sorted(demands):
            demand = demands[importer]
            if demand <= 0:
                continue
            for exporter in sorted(supplies, key=lambda tag: (-supplies[tag], tag)):
                if exporter == importer or supplies[exporter] <= 0 or frozenset((exporter, importer)) in embargoes:
                    continue
                is_common_pair = exporter in common_peers.get(importer, set())
                if common_only != is_common_pair:
                    continue
                amount = min(demand, supplies[exporter])
                if amount <= 0:
                    continue
                flows.append({
                    "exporter_id": exporter,
                    "importer_id": importer,
                    "game_resource_id": resource,
                    "trade_value_usd": amount,
                })
                supplies[exporter] -= amount
                demands[importer] -= amount
                demand -= amount
                if demand <= 0:
                    break

    def _constraints(self, effects: pl.DataFrame) -> tuple[dict[str, set[str]], set[frozenset[str]]]:
        common_peers: dict[str, set[str]] = defaultdict(set)
        embargoes: set[frozenset[str]] = set()
        for effect in effects.to_dicts():
            country = self._tag(effect.get("country_id"))
            peers = self._detail_tags(effect.get("detail"))
            if str(effect.get("effect") or "") == "common_market_priority":
                common_peers[country].update(peers)
            elif str(effect.get("effect") or "") == "resource_trade_embargo":
                embargoes.update(frozenset((country, peer)) for peer in peers if peer != country)
        return common_peers, embargoes

    def _detail_tags(self, value: Any) -> tuple[str, ...]:
        try:
            parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return ()
        if not isinstance(parsed, list):
            return ()
        return tuple(sorted({self._tag(item) for item in parsed if self._tag(item)}))

    def _tag(self, value: Any) -> str:
        return str(value or "").strip().upper()

    def _number(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
