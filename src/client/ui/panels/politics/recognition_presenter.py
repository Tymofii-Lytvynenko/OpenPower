"""Read-only projection of recognition cases for the diplomacy interface."""

from __future__ import annotations

import math

import polars as pl


class RecognitionPresenter:
    def cases_for_country(self, state, country_tag: str) -> list[dict]:
        cases = state.tables.get("recognition_cases")
        if cases is None or cases.is_empty():
            return []
        country_id = str(country_tag or "").strip().upper()
        votes = state.tables.get("recognition_votes")
        vote_by_case: dict[tuple[str, str], str] = {}
        if votes is not None and not votes.is_empty():
            vote_by_case = {
                (str(row.get("case_id") or ""), str(row.get("country_id") or "").upper()): str(row.get("vote") or "")
                for row in votes.iter_rows(named=True)
            }
        statuses = state.tables.get("regional_recognition_status")
        status_by_case: dict[tuple[str, str], str] = {}
        if statuses is not None and not statuses.is_empty():
            status_by_case = {
                (str(row.get("case_id") or ""), str(row.get("country_id") or "").upper()): str(row.get("status") or "")
                for row in statuses.iter_rows(named=True)
            }
        rows: list[dict] = []
        for row in cases.iter_rows(named=True):
            case_id = str(row.get("id") or "")
            voter_ids = tuple(str(value).upper() for value in row.get("eligible_voters") or [])
            case_votes = [
                vote_by_case[(case_id, voter_id)]
                for voter_id in voter_ids
                if (case_id, voter_id) in vote_by_case
            ]
            rows.append(
                {
                    "id": case_id,
                    "region_id": int(row.get("region_id") or 0),
                    "claimant_id": str(row.get("claimant_id") or ""),
                    "former_owner_id": str(row.get("former_owner_id") or ""),
                    "status": str(row.get("status") or "pending"),
                    "deadline_at_minute": int(row.get("deadline_at_minute") or 0),
                    "days_remaining": max(
                        0,
                        math.ceil(
                            (int(row.get("deadline_at_minute") or 0) - int(state.time.total_minutes))
                            / 1_440
                        ),
                    ),
                    "eligible_voters": voter_ids,
                    "yes_votes": sum(vote == "yes" for vote in case_votes),
                    "no_votes": sum(vote == "no" for vote in case_votes),
                    "abstain_votes": sum(vote == "abstain" for vote in case_votes),
                    "my_vote": vote_by_case.get((case_id, country_id), ""),
                    "my_status": status_by_case.get((case_id, country_id), ""),
                    "reason": str(row.get("reason") or ""),
                }
            )
        return sorted(rows, key=lambda item: (item["deadline_at_minute"], item["id"]))

    def for_region(self, state, region_id: int, country_tag: str) -> dict | None:
        cases = state.tables.get("recognition_cases")
        if cases is None or cases.is_empty() or "region_id" not in cases.columns:
            return None
        matches = cases.filter(pl.col("region_id") == int(region_id)).sort(
            ["opened_at_minute", "id"], descending=[True, True]
        )
        if matches.is_empty():
            return None
        case = matches.row(0, named=True)
        case_id = str(case.get("id") or "")
        statuses = state.tables.get("regional_recognition_status")
        case_statuses = (
            statuses.filter(pl.col("case_id") == case_id).to_dicts()
            if statuses is not None and not statuses.is_empty() and "case_id" in statuses.columns
            else []
        )
        country_id = str(country_tag or "").strip().upper()
        selected = next(
            (row for row in case_statuses if str(row.get("country_id") or "").upper() == country_id),
            None,
        )
        return {
            "case_id": case_id,
            "region_id": int(case.get("region_id") or 0),
            "claimant_id": str(case.get("claimant_id") or ""),
            "former_owner_id": str(case.get("former_owner_id") or ""),
            "status": str(case.get("status") or "pending"),
            "eligible_count": len(case.get("eligible_voters") or []),
            "yes_votes": int(case.get("yes_votes") or 0),
            "recognized_count": sum(row.get("status") == "recognized" for row in case_statuses),
            "country_status": str(selected.get("status") or "") if selected else "",
        }
