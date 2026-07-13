"""Authorization rules for cross-border military-unit purchases."""

from __future__ import annotations

import json
from typing import Any

import polars as pl


class WeaponsTradePolicy:
    """Applies treaty access and embargoes before a foreign weapons order is accepted."""

    def can_order(
        self,
        effects: pl.DataFrame | None,
        buyer_country_id: str,
        seller_country_id: str,
        eligibility: str,
    ) -> bool:
        buyer, seller = self._tag(buyer_country_id), self._tag(seller_country_id)
        if not buyer or not seller or buyer == seller or self._is_embargoed(effects, buyer, seller):
            return False
        access_required = str(eligibility or "open").strip().lower() in {"treaty", "members", "members_only"}
        return not access_required or self._has_access(effects, buyer, seller)

    def _is_embargoed(self, effects: pl.DataFrame | None, buyer: str, seller: str) -> bool:
        return self._has_peer_effect(effects, "weapons_trade_embargo", buyer, seller)

    def _has_access(self, effects: pl.DataFrame | None, buyer: str, seller: str) -> bool:
        return self._has_peer_effect(effects, "weapons_market_access", buyer, seller)

    def _has_peer_effect(self, effects: pl.DataFrame | None, effect_name: str, country: str, peer: str) -> bool:
        if effects is None or effects.is_empty():
            return False
        for row in effects.filter(pl.col("effect") == effect_name).iter_rows(named=True):
            if self._tag(row.get("country_id")) == country and peer in self._detail_tags(row.get("detail")):
                return True
        return False

    def _detail_tags(self, value: Any) -> set[str]:
        try:
            parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return set()
        return {self._tag(item) for item in parsed if self._tag(item)} if isinstance(parsed, list) else set()

    def _tag(self, value: Any) -> str:
        return str(value or "").strip().upper()
