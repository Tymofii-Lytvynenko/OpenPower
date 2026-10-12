"""Validation, valuation, and atomic execution for bilateral trade packages."""

from __future__ import annotations

import json
import math
from typing import Any

import polars as pl

MAX_ASSETS_PER_SIDE = 16
MAX_CASH_AMOUNT = 1e18


def normalize_trade_assets(raw_assets: Any) -> tuple[list[dict[str, Any]], str]:
    if not isinstance(raw_assets, (list, tuple)) or len(raw_assets) > MAX_ASSETS_PER_SIDE:
        return [], "Each side can contain at most 16 assets."
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    cash_total = 0.0
    for raw in raw_assets:
        if not isinstance(raw, dict):
            return [], "Trade assets must be structured values."
        asset_type = str(raw.get("type") or "").strip().casefold()
        if asset_type == "cash":
            amount = _finite(raw.get("amount"))
            if amount <= 0.0 or amount > MAX_CASH_AMOUNT:
                return [], "Cash amounts must be finite, positive, and within the supported limit."
            cash_total += round(amount, 2)
            continue
        if asset_type == "territory":
            try:
                region_id = int(raw.get("region_id"))
            except (TypeError, ValueError, OverflowError):
                return [], "Territory assets need a valid region id."
            if region_id <= 0:
                return [], "Territory assets need a positive region id."
            key = (asset_type, str(region_id))
            asset = {"type": asset_type, "region_id": region_id}
        elif asset_type == "technology":
            branch = str(raw.get("branch") or "").strip().casefold()
            try:
                level = int(raw.get("level"))
            except (TypeError, ValueError, OverflowError):
                return [], "Technology assets need a valid research level."
            if not branch or level < 1:
                return [], "Technology assets need a branch and a positive research level."
            key = (asset_type, branch)
            asset = {"type": asset_type, "branch": branch, "level": level}
        else:
            return [], "Supported assets are cash, territory, and technology."
        if key in seen:
            return [], "A package cannot offer the same territory or technology branch twice."
        seen.add(key)
        normalized.append(asset)
    if cash_total > 0.0:
        if not math.isfinite(cash_total) or cash_total > MAX_CASH_AMOUNT:
            return [], "The combined cash amount is outside the supported limit."
        normalized.append({"type": "cash", "amount": round(cash_total, 2)})
    return normalized, ""


def decode_trade_assets(raw_json: Any) -> list[dict[str, Any]]:
    try:
        raw = json.loads(str(raw_json or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    assets, error = normalize_trade_assets(raw)
    return [] if error else assets


def validate_trade_packages(
    source_country_id: str,
    target_country_id: str,
    offered_assets: list[dict[str, Any]],
    requested_assets: list[dict[str, Any]],
    countries: list[dict[str, Any]],
    regions: list[dict[str, Any]],
    governments: list[dict[str, Any]],
    research_tracks: list[dict[str, Any]],
    occupations: list[dict[str, Any]],
) -> str:
    if not offered_assets and not requested_assets:
        return "A trade package must contain at least one asset."
    country_by_id = {_tag(row.get("id")): row for row in countries}
    if source_country_id not in country_by_id or target_country_id not in country_by_id:
        return "Both countries must exist in the current world."
    region_by_id = {_integer(row.get("id")): row for row in regions}
    government_by_id = {_tag(row.get("country_id")): row for row in governments}
    track_by_branch = {
        (_tag(row.get("country_id")), _branch(row.get("branch"))): row
        for row in research_tracks
    }
    occupied = {_integer(row.get("region_id")) for row in occupations}

    for owner, assets in ((source_country_id, offered_assets), (target_country_id, requested_assets)):
        if not assets:
            continue
        cash = sum(_finite(asset.get("amount")) for asset in assets if asset.get("type") == "cash")
        if cash > _finite(country_by_id[owner].get("money_reserves")) + 0.005:
            return f"{owner} does not have enough available cash for this package."

        outgoing_regions = [
            _integer(asset.get("region_id")) for asset in assets if asset.get("type") == "territory"
        ]
        owned_regions = {
            _integer(region.get("id"))
            for region in regions
            if _tag(region.get("owner")) == owner
        }
        if len(owned_regions - set(outgoing_regions)) < 1:
            return f"{owner} must keep at least one region."
        capital_id = _integer(government_by_id.get(owner, {}).get("capital_region_id"))
        for region_id in outgoing_regions:
            region = region_by_id.get(region_id)
            if region is None or _tag(region.get("owner")) != owner:
                return f"{owner} no longer owns territory {region_id}."
            if region_id in occupied:
                return f"Occupied territory {region_id} cannot be transferred through a trade."
            if region_id == capital_id and len(owned_regions) <= 1:
                return f"{owner} cannot transfer its only capital region."

        for asset in assets:
            if asset.get("type") != "technology":
                continue
            branch = _branch(asset.get("branch"))
            seller = track_by_branch.get((owner, branch))
            receiver = track_by_branch.get((target_country_id if owner == source_country_id else source_country_id, branch))
            offered_level = _integer(asset.get("level"))
            if seller is None or _integer(seller.get("research_level")) != offered_level:
                return f"Technology offers must transfer {owner}'s current {branch} level in full."
            if receiver is not None and _integer(receiver.get("research_level")) >= offered_level:
                return f"The receiving country already has {branch} at level {offered_level} or higher."
    return ""


def apply_trade_packages(
    source_country_id: str,
    target_country_id: str,
    offered_assets: list[dict[str, Any]],
    requested_assets: list[dict[str, Any]],
    countries: list[dict[str, Any]],
    regions: list[dict[str, Any]],
    governments: list[dict[str, Any]],
    research_tracks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    country_by_id = {_tag(row.get("id")): row for row in countries}
    region_by_id = {_integer(row.get("id")): row for row in regions}
    government_by_id = {_tag(row.get("country_id")): row for row in governments}
    track_by_key = {
        (_tag(row.get("country_id")), _branch(row.get("branch"))): row
        for row in research_tracks
    }

    for giver, receiver, assets in (
        (source_country_id, target_country_id, offered_assets),
        (target_country_id, source_country_id, requested_assets),
    ):
        for asset in assets:
            if asset["type"] == "cash":
                amount = _finite(asset.get("amount"))
                country_by_id[giver]["money_reserves"] = _finite(country_by_id[giver].get("money_reserves")) - amount
                country_by_id[receiver]["money_reserves"] = _finite(country_by_id[receiver].get("money_reserves")) + amount
            elif asset["type"] == "territory":
                region_by_id[_integer(asset.get("region_id"))]["owner"] = receiver
            elif asset["type"] == "technology":
                branch = _branch(asset.get("branch"))
                offered_level = _integer(asset.get("level"))
                seller = track_by_key[(giver, branch)]
                receiver_key = (receiver, branch)
                recipient = track_by_key.get(receiver_key)
                if recipient is None:
                    recipient = dict(seller)
                    recipient.update(
                        {
                            "id": f"{receiver}-{branch}",
                            "country_id": receiver,
                            "branch": branch,
                            "funding_ratio": 0.0,
                            "progress": 0.0,
                            "priority": 1,
                            "focus": "",
                            "research_level": offered_level,
                            "blocking_reason": "",
                        }
                    )
                    research_tracks.append(recipient)
                    track_by_key[receiver_key] = recipient
                else:
                    recipient["research_level"] = max(
                        _integer(recipient.get("research_level")), offered_level
                    )
                try:
                    seller_unlocks = json.loads(str(seller.get("unlocks_json") or "[]"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    seller_unlocks = []
                try:
                    recipient_unlocks = json.loads(str(recipient.get("unlocks_json") or "[]"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    recipient_unlocks = []
                if isinstance(seller_unlocks, list) and isinstance(recipient_unlocks, list):
                    recipient["unlocks_json"] = json.dumps(
                        sorted({str(value) for value in recipient_unlocks + seller_unlocks}),
                        separators=(",", ":"),
                    )

    for owner in (source_country_id, target_country_id):
        government = government_by_id.get(owner)
        if government is None:
            continue
        capital_id = _integer(government.get("capital_region_id"))
        current_capital = region_by_id.get(capital_id)
        if current_capital is None or _tag(current_capital.get("owner")) != owner:
            replacement_ids = sorted(
                region_id
                for region_id, region in region_by_id.items()
                if _tag(region.get("owner")) == owner
            )
            government["capital_region_id"] = replacement_ids[0] if replacement_ids else 0

    return list(country_by_id.values()), list(region_by_id.values()), governments, research_tracks


def trade_package_value(
    assets: list[dict[str, Any]],
    giver: str,
    receiver: str,
    countries: list[dict[str, Any]],
    regions: list[dict[str, Any]],
    research_tracks: list[dict[str, Any]],
) -> float:
    giver_country = next((row for row in countries if _tag(row.get("id")) == giver), {})
    receiver_country = next((row for row in countries if _tag(row.get("id")) == receiver), {})
    giver_gdp = max(1.0, _finite(giver_country.get("gdp")))
    receiver_gdp = max(1.0, _finite(receiver_country.get("gdp")))
    owned_region_count = max(
        1,
        sum(1 for row in regions if _tag(row.get("owner")) == giver),
    )
    tracks = {
        (_tag(row.get("country_id")), _branch(row.get("branch"))): row
        for row in research_tracks
    }
    total = 0.0
    for asset in assets:
        if asset["type"] == "cash":
            total += _finite(asset.get("amount"))
        elif asset["type"] == "territory":
            total += giver_gdp / owned_region_count
        elif asset["type"] == "technology":
            current_level = _integer(tracks.get((receiver, _branch(asset.get("branch"))), {}).get("research_level"))
            additional_levels = max(0, _integer(asset.get("level")) - current_level)
            total += receiver_gdp * 0.02 * additional_levels
    return total


def validate_trade_package_frames(
    source_country_id: str,
    target_country_id: str,
    offered_assets: list[dict[str, Any]],
    requested_assets: list[dict[str, Any]],
    countries: pl.DataFrame,
    regions: pl.DataFrame,
    governments: pl.DataFrame | None,
    research_tracks: pl.DataFrame | None,
    occupations: pl.DataFrame | None,
) -> str:
    """Validate a bounded package against authoritative frames without row expansion."""

    if not offered_assets and not requested_assets:
        return "A trade package must contain at least one asset."
    source_country = _frame_row_by_tag(countries, "id", source_country_id)
    target_country = _frame_row_by_tag(countries, "id", target_country_id)
    if source_country is None or target_country is None:
        return "Both countries must exist in the current world."
    for owner, assets in ((source_country_id, offered_assets), (target_country_id, requested_assets)):
        if not assets:
            continue
        country = source_country if owner == source_country_id else target_country
        cash = sum(_finite(asset.get("amount")) for asset in assets if asset.get("type") == "cash")
        if cash > _finite(country.get("money_reserves")) + 0.005:
            return f"{owner} does not have enough available cash for this package."

        outgoing_regions = [
            _integer(asset.get("region_id")) for asset in assets if asset.get("type") == "territory"
        ]
        owned = regions.filter(
            pl.col("owner").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase() == owner
        ).select(pl.col("id").cast(pl.Int64, strict=False)).unique()
        remaining_owned = owned.filter(~pl.col("id").is_in(outgoing_regions)).height
        if remaining_owned < 1:
            return f"{owner} must keep at least one region."
        government = _frame_row_by_tag(governments, "country_id", owner)
        capital_id = _integer(None if government is None else government.get("capital_region_id"))
        for region_id in outgoing_regions:
            region = _frame_row_by_integer(regions, "id", region_id)
            if region is None or _tag(region.get("owner")) != owner:
                return f"{owner} no longer owns territory {region_id}."
            if occupations is not None and "region_id" in occupations.columns:
                if not occupations.filter(pl.col("region_id").cast(pl.Int64, strict=False) == region_id).is_empty():
                    return f"Occupied territory {region_id} cannot be transferred through a trade."
            if region_id == capital_id and owned.height <= 1:
                return f"{owner} cannot transfer its only capital region."

        receiver = target_country_id if owner == source_country_id else source_country_id
        for asset in assets:
            if asset.get("type") != "technology":
                continue
            branch = _branch(asset.get("branch"))
            seller = _frame_track_row(research_tracks, owner, branch)
            recipient = _frame_track_row(research_tracks, receiver, branch)
            offered_level = _integer(asset.get("level"))
            if seller is None or _integer(seller.get("research_level")) != offered_level:
                return f"Technology offers must transfer {owner}'s current {branch} level in full."
            if recipient is not None and _integer(recipient.get("research_level")) >= offered_level:
                return f"The receiving country already has {branch} at level {offered_level} or higher."
    return ""


def apply_trade_package_frames(
    source_country_id: str,
    target_country_id: str,
    offered_assets: list[dict[str, Any]],
    requested_assets: list[dict[str, Any]],
    countries: pl.DataFrame,
    regions: pl.DataFrame,
    governments: pl.DataFrame | None,
    research_tracks: pl.DataFrame | None,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame | None, pl.DataFrame | None]:
    """Apply the small package edits directly to the authoritative table frames."""

    for giver, receiver, assets in (
        (source_country_id, target_country_id, offered_assets),
        (target_country_id, source_country_id, requested_assets),
    ):
        for asset in assets:
            if asset["type"] == "cash":
                amount = _finite(asset.get("amount"))
                if "money_reserves" in countries.columns:
                    owner = pl.col("id").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase()
                    reserves = _finite_frame_column("money_reserves")
                    countries = countries.with_columns(
                        pl.when(owner == giver)
                        .then(reserves - amount)
                        .when(owner == receiver)
                        .then(reserves + amount)
                        .otherwise(pl.col("money_reserves"))
                        .cast(countries.schema["money_reserves"], strict=False)
                        .alias("money_reserves")
                    )
            elif asset["type"] == "territory":
                region_id = _integer(asset.get("region_id"))
                if "owner" in regions.columns:
                    regions = regions.with_columns(
                        pl.when(pl.col("id").cast(pl.Int64, strict=False) == region_id)
                        .then(pl.lit(receiver))
                        .otherwise(pl.col("owner"))
                        .alias("owner")
                    )
            elif asset["type"] == "technology" and research_tracks is not None:
                branch = _branch(asset.get("branch"))
                offered_level = _integer(asset.get("level"))
                seller = _frame_track_row(research_tracks, giver, branch)
                if seller is None:
                    continue
                recipient = _frame_track_row(research_tracks, receiver, branch)
                if recipient is None:
                    recipient = dict(seller)
                    recipient.update(
                        {
                            "id": f"{receiver}-{branch}",
                            "country_id": receiver,
                            "branch": branch,
                            "funding_ratio": 0.0,
                            "progress": 0.0,
                            "priority": 1,
                            "focus": "",
                            "research_level": offered_level,
                            "blocking_reason": "",
                        }
                    )
                    research_tracks = pl.concat(
                        [research_tracks, pl.DataFrame([recipient], schema=research_tracks.schema, strict=False)],
                        how="vertical",
                    )
                    recipient_id = str(recipient.get("id") or "")
                else:
                    recipient_id = str(recipient.get("id") or "")
                    if "research_level" in research_tracks.columns:
                        research_tracks = research_tracks.with_columns(
                            pl.when(pl.col("id").cast(pl.Utf8, strict=False) == recipient_id)
                            .then(pl.max_horizontal(
                                pl.col("research_level").cast(pl.Int64, strict=False).fill_null(0),
                                pl.lit(offered_level),
                            ))
                            .otherwise(pl.col("research_level"))
                            .cast(research_tracks.schema["research_level"], strict=False)
                            .alias("research_level")
                        )
                if "unlocks_json" in research_tracks.columns:
                    seller_unlocks = _json_string_list(seller.get("unlocks_json"))
                    recipient_unlocks = _json_string_list(recipient.get("unlocks_json"))
                    unlocks = json.dumps(
                        sorted(set(recipient_unlocks + seller_unlocks)), separators=(",", ":")
                    )
                    research_tracks = research_tracks.with_columns(
                        pl.when(pl.col("id").cast(pl.Utf8, strict=False) == recipient_id)
                        .then(pl.lit(unlocks))
                        .otherwise(pl.col("unlocks_json"))
                        .alias("unlocks_json")
                    )

    if governments is not None and regions is not None and {"country_id", "capital_region_id"}.issubset(governments.columns):
        for owner in (source_country_id, target_country_id):
            government = _frame_row_by_tag(governments, "country_id", owner)
            if government is None:
                continue
            capital_id = _integer(government.get("capital_region_id"))
            capital = _frame_row_by_integer(regions, "id", capital_id)
            if capital is not None and _tag(capital.get("owner")) == owner:
                continue
            replacement = (
                regions.filter(
                    pl.col("owner").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase() == owner
                )
                .select(pl.col("id").cast(pl.Int64, strict=False))
                .sort("id")
                .head(1)
            )
            new_capital = int(replacement.item() or 0) if not replacement.is_empty() else 0
            governments = governments.with_columns(
                pl.when(
                    pl.col("country_id").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase() == owner
                )
                .then(pl.lit(new_capital).cast(governments.schema["capital_region_id"], strict=False))
                .otherwise(pl.col("capital_region_id"))
                .alias("capital_region_id")
            )
    return countries, regions, governments, research_tracks


def trade_package_value_frames(
    assets: list[dict[str, Any]],
    giver: str,
    receiver: str,
    countries: pl.DataFrame | None,
    regions: pl.DataFrame | None,
    research_tracks: pl.DataFrame | None,
) -> float:
    """Value a bounded package using scalar lookups and frame aggregates."""

    giver_country = _frame_row_by_tag(countries, "id", giver)
    receiver_country = _frame_row_by_tag(countries, "id", receiver)
    giver_gdp = max(1.0, _finite(None if giver_country is None else giver_country.get("gdp")))
    receiver_gdp = max(1.0, _finite(None if receiver_country is None else receiver_country.get("gdp")))
    owned_count = 1
    if regions is not None and {"owner", "id"}.issubset(regions.columns):
        owned_count = max(
            1,
            regions.filter(
                pl.col("owner").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase() == giver
            ).select(pl.col("id").n_unique()).item() or 0,
        )
    total = 0.0
    for asset in assets:
        if asset["type"] == "cash":
            total += _finite(asset.get("amount"))
        elif asset["type"] == "territory":
            total += giver_gdp / owned_count
        elif asset["type"] == "technology":
            recipient = _frame_track_row(research_tracks, receiver, _branch(asset.get("branch")))
            current_level = _integer(None if recipient is None else recipient.get("research_level"))
            additional_levels = max(0, _integer(asset.get("level")) - current_level)
            total += receiver_gdp * 0.02 * additional_levels
    return total


def _frame_row_by_tag(frame: pl.DataFrame | None, key_column: str, key: str) -> dict[str, Any] | None:
    if frame is None or key_column not in frame.columns:
        return None
    matches = frame.filter(
        pl.col(key_column).cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase()
        == _tag(key)
    )
    return matches.row(matches.height - 1, named=True) if not matches.is_empty() else None


def _frame_row_by_integer(frame: pl.DataFrame | None, key_column: str, key: int) -> dict[str, Any] | None:
    if frame is None or key_column not in frame.columns:
        return None
    matches = frame.filter(pl.col(key_column).cast(pl.Int64, strict=False) == key)
    return matches.row(matches.height - 1, named=True) if not matches.is_empty() else None


def _frame_track_row(frame: pl.DataFrame | None, country: str, branch: str) -> dict[str, Any] | None:
    if frame is None or not {"country_id", "branch"}.issubset(frame.columns):
        return None
    matches = frame.filter(
        (pl.col("country_id").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase() == _tag(country))
        & (pl.col("branch").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_lowercase() == _branch(branch))
    )
    return matches.row(matches.height - 1, named=True) if not matches.is_empty() else None


def _finite_frame_column(column: str) -> pl.Expr:
    value = pl.col(column).cast(pl.Float64, strict=False)
    return pl.when(value.is_finite()).then(value).otherwise(0.0)


def _json_string_list(value: Any) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def encode_trade_assets(assets: list[dict[str, Any]]) -> str:
    return json.dumps(assets, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _tag(value: Any) -> str:
    return str(value or "").strip().upper()


def _branch(value: Any) -> str:
    return str(value or "").strip().casefold()


def _integer(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def _finite(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return number if math.isfinite(number) else 0.0
