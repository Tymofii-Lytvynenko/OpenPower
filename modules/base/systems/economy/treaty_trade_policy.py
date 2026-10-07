"""Deterministic bilateral resource allocation under treaty constraints."""

from __future__ import annotations

import heapq
import json
import math
from collections import defaultdict
from typing import Any, Callable

import polars as pl


TRADE_FLOW_SCHEMA = {
    "exporter_id": pl.Utf8,
    "importer_id": pl.Utf8,
    "game_resource_id": pl.Utf8,
    "trade_value_usd": pl.Float64,
}

REGIONAL_TRADE_FLOW_SCHEMA = {
    **TRADE_FLOW_SCHEMA,
    "source_region_id": pl.Int32,
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
        for resource_id, resource_market in market.sort(
            ["game_resource_id", "country_id"]
        ).group_by("game_resource_id", maintain_order=True):
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

    def allocate_with_regional_sources(
        self,
        market: pl.DataFrame,
        effects: pl.DataFrame,
        regional_production: pl.DataFrame,
        regional_access: Callable[[int, str, str], bool],
    ) -> pl.DataFrame:
        """Allocate bilateral demand without erasing explicitly declared source regions."""

        required_market_columns = {
            "country_id",
            "game_resource_id",
            "export_desired",
            "affordable_import",
        }
        required_production_columns = {
            "country_id",
            "region_id",
            "game_resource_id",
            "domestic_production",
        }
        if not required_market_columns.issubset(market.columns):
            raise ValueError("Regional trade allocation requires complete market supply and demand columns.")
        if not required_production_columns.issubset(regional_production.columns):
            raise ValueError("Regional production records are missing required provenance columns.")

        common_peers, embargoes = self._constraints(effects)
        exports: dict[tuple[str, str], float] = defaultdict(float)
        demands: dict[tuple[str, str], float] = defaultdict(float)
        national_production: dict[tuple[str, str], float] = defaultdict(float)
        has_national_production = "domestic_production" in market.columns
        for row in market.select(sorted(required_market_columns)).sort(
            ["game_resource_id", "country_id"]
        ).to_dicts():
            key = (self._tag(row.get("country_id")), str(row.get("game_resource_id") or ""))
            exports[key] += self._finite_nonnegative(row.get("export_desired"))
            demands[key] += self._finite_nonnegative(row.get("affordable_import"))
        if has_national_production:
            for row in market.select(
                "country_id", "game_resource_id", "domestic_production"
            ).to_dicts():
                key = (self._tag(row.get("country_id")), str(row.get("game_resource_id") or ""))
                national_production[key] += self._finite_nonnegative(row.get("domestic_production"))

        regional_supply: dict[tuple[str, str], dict[int, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        for row in regional_production.select(sorted(required_production_columns)).sort(
            ["game_resource_id", "country_id", "region_id"]
        ).to_dicts():
            key = (self._tag(row.get("country_id")), str(row.get("game_resource_id") or ""))
            try:
                region_id = int(row.get("region_id") or 0)
            except (TypeError, ValueError, OverflowError):
                raise ValueError("Regional production has an invalid source region ID.")
            if region_id <= 0:
                raise ValueError("Regional production requires a positive source region ID.")
            amount = self._validated_nonnegative(
                row.get("domestic_production"),
                "Regional production must be finite and non-negative.",
            )
            if key[0] and key[1] and amount > 0.0:
                if key not in exports:
                    raise ValueError(
                        f"Regional production for {key[0]}/{key[1]} has no national market row."
                    )
                regional_supply[key][region_id] += amount

        if has_national_production:
            for key, sources in regional_supply.items():
                if sum(sources.values()) > national_production.get(key, 0.0) + 1e-9:
                    raise ValueError(
                        f"Explicit regional output exceeds national production for {key[0]}/{key[1]}."
                    )

        resources = sorted({resource for _, resource in exports} | {resource for _, resource in demands})
        flows: list[dict[str, Any]] = []
        for resource in resources:
            lots: list[dict[str, Any]] = []
            resource_countries = sorted(
                {country for country, item_resource in exports if item_resource == resource}
                | {country for country, item_resource in demands if item_resource == resource}
            )
            for country in resource_countries:
                available = exports.get((country, resource), 0.0)
                regional_by_id = regional_supply.get((country, resource), {})
                declared_total = sum(regional_by_id.values())
                tagged_total = min(available, declared_total)
                scale = tagged_total / declared_total if declared_total > 0.0 else 0.0
                for region_id, amount in sorted(regional_by_id.items()):
                    tagged_amount = amount * scale
                    if tagged_amount > 0.0:
                        lots.append({
                            "exporter": country,
                            "region_id": region_id,
                            "amount": tagged_amount,
                        })
                unassigned = max(0.0, available - tagged_total)
                if unassigned > 0.0:
                    lots.append({"exporter": country, "region_id": None, "amount": unassigned})

            resource_demands = {
                country: amount
                for (country, item_resource), amount in demands.items()
                if item_resource == resource and amount > 0.0
            }
            ordered_lots = sorted(
                lots,
                key=lambda lot: (
                    -lot["amount"],
                    lot["exporter"],
                    -1 if lot["region_id"] is None else lot["region_id"],
                ),
            )

            for common_only in (True, False):
                for importer in sorted(resource_demands):
                    demand = resource_demands[importer]
                    if demand <= 0.0:
                        continue
                    for lot in ordered_lots:
                        exporter = lot["exporter"]
                        amount = lot["amount"]
                        preferred = exporter in common_peers.get(importer, set())
                        if (
                            amount <= 0.0
                            or exporter == importer
                            or (common_only and not preferred)
                            or (not common_only and preferred)
                            or frozenset((exporter, importer)) in embargoes
                        ):
                            continue
                        region_id = lot["region_id"]
                        if region_id is not None and not regional_access(
                            region_id, exporter, importer
                        ):
                            continue
                        allocated = min(demand, amount)
                        if allocated <= 0.0:
                            continue
                        flows.append(
                            {
                                "exporter_id": exporter,
                                "importer_id": importer,
                                "game_resource_id": resource,
                                "trade_value_usd": allocated,
                                "source_region_id": region_id,
                            }
                        )
                        lot["amount"] -= allocated
                        demand -= allocated
                        resource_demands[importer] = demand
                        if demand <= 0.0:
                            break

        return (
            pl.DataFrame(flows, schema=REGIONAL_TRADE_FLOW_SCHEMA, strict=False)
            if flows
            else pl.DataFrame(schema=REGIONAL_TRADE_FLOW_SCHEMA)
        )

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
        if common_only:
            self._allocate_common_market(
                flows,
                resource,
                supplies,
                demands,
                common_peers,
                embargoes,
            )
            return
        self._allocate_general_market(
            flows,
            resource,
            supplies,
            demands,
            common_peers,
            embargoes,
        )

    def _allocate_common_market(
        self,
        flows: list[dict[str, Any]],
        resource: str,
        supplies: dict[str, float],
        demands: dict[str, float],
        common_peers: dict[str, set[str]],
        embargoes: set[frozenset[str]],
    ) -> None:
        for importer in sorted(demands):
            demand = demands[importer]
            if demand <= 0.0:
                continue
            exporters = sorted(
                common_peers.get(importer, ()),
                key=lambda tag: (-supplies.get(tag, 0.0), tag),
            )
            for exporter in exporters:
                if (
                    exporter == importer
                    or supplies.get(exporter, 0.0) <= 0.0
                    or frozenset((exporter, importer)) in embargoes
                ):
                    continue
                demand = self._record_flow(
                    flows,
                    resource,
                    exporter,
                    importer,
                    demand,
                    supplies,
                    demands,
                )
                if demand <= 0.0:
                    break

    def _allocate_general_market(
        self,
        flows: list[dict[str, Any]],
        resource: str,
        supplies: dict[str, float],
        demands: dict[str, float],
        common_peers: dict[str, set[str]],
        embargoes: set[frozenset[str]],
    ) -> None:
        supply_heap = [
            (-amount, exporter)
            for exporter, amount in supplies.items()
            if amount > 0.0
        ]
        heapq.heapify(supply_heap)
        for importer in sorted(demands):
            demand = demands[importer]
            if demand <= 0.0:
                continue
            deferred: list[tuple[float, str]] = []
            while demand > 0.0 and supply_heap:
                _, exporter = heapq.heappop(supply_heap)
                supply = supplies.get(exporter, 0.0)
                if supply <= 0.0:
                    continue
                if (
                    exporter == importer
                    or exporter in common_peers.get(importer, set())
                    or frozenset((exporter, importer)) in embargoes
                ):
                    deferred.append((-supply, exporter))
                    continue
                demand = self._record_flow(
                    flows,
                    resource,
                    exporter,
                    importer,
                    demand,
                    supplies,
                    demands,
                )
                if supplies[exporter] > 0.0:
                    deferred.append((-supplies[exporter], exporter))
            for entry in deferred:
                heapq.heappush(supply_heap, entry)

    def _record_flow(
        self,
        flows: list[dict[str, Any]],
        resource: str,
        exporter: str,
        importer: str,
        demand: float,
        supplies: dict[str, float],
        demands: dict[str, float],
    ) -> float:
        amount = min(demand, supplies[exporter])
        if amount <= 0.0:
            return demand
        flows.append({
            "exporter_id": exporter,
            "importer_id": importer,
            "game_resource_id": resource,
            "trade_value_usd": amount,
        })
        supplies[exporter] -= amount
        demands[importer] -= amount
        return demand - amount

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

    def _finite_nonnegative(self, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return number if math.isfinite(number) and number > 0.0 else 0.0

    def _validated_nonnegative(self, value: Any, message: str) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(message) from error
        if not math.isfinite(number) or number < 0.0:
            raise ValueError(message)
        return number
