"""Build gameplay-only PIP poverty estimates for countries without 2001 surveys."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "modules/base/data"
COUNTRIES_PATH = DATA_DIR / "countries/countries.tsv"
DEMOGRAPHICS_PATH = DATA_DIR / "countries/countries_dem.tsv"
PIP_PATH = DATA_DIR / "countries/countries_poverty_international_2001.tsv"
HDI_BACKFILLS_PATH = DATA_DIR / "sources/2001/hdi_backfills_2001.tsv"
GNI_SOURCE_PATH = DATA_DIR / "sources/2001/NY.GNP.PCAP.PP.CD_2001.json"
OUTPUT_PATH = DATA_DIR / "countries/countries_poverty_scenario_estimates_2001.tsv"

PIP_VALUE = "historical_poverty_global_3usd_2021_ppp_pct"
PIP_AVAILABLE = f"{PIP_VALUE}_available"
PIP_SURVEY_YEAR = f"{PIP_VALUE}_survey_year"
PIP_SOURCE_VERSION = "20260922_2021_01_02_PROD"
PIP_API_URL = "https://api.worldbank.org/pip/v1/pip"
GNI_INDICATOR = "NY.GNP.PCAP.PP.CD"
GNI_API_URL = (
    "https://api.worldbank.org/v2/country/all/indicator/NY.GNP.PCAP.PP.CD"
    "?date=2001&format=json&per_page=1000"
)
HDI_SOURCE_URL = (
    "https://hdr.undp.org/sites/default/files/2025_HDR/"
    "HDR25_Composite_indices_complete_time_series.csv"
)
NEIGHBOR_COUNT = 5
DISTANCE_OFFSET = 0.25

OUTPUT_COLUMNS = (
    "id",
    "gameplay_poverty_estimate_3usd_2021_ppp_pct",
    "gameplay_poverty_estimate_3usd_2021_ppp_pct_available",
    "gameplay_poverty_estimate_3usd_2021_ppp_scenario_year",
    "gameplay_poverty_estimate_3usd_2021_ppp_line_usd_per_person_per_day",
    "gameplay_poverty_estimate_3usd_2021_ppp_line_ppp_year",
    "gameplay_poverty_estimate_3usd_2021_ppp_type",
    "gameplay_poverty_estimate_3usd_2021_ppp_method",
    "gameplay_poverty_estimate_3usd_2021_ppp_training_observation_count",
    "gameplay_poverty_estimate_3usd_2021_ppp_nearest_training_ids",
    "gameplay_poverty_estimate_3usd_2021_ppp_nearest_training_distance",
    "gameplay_poverty_estimate_3usd_2021_ppp_hdi_input_2001",
    "gameplay_poverty_estimate_3usd_2021_ppp_hdi_input_quality",
    "gameplay_poverty_estimate_3usd_2021_ppp_gni_per_capita_ppp_current_intl_dollars_2001",
    "gameplay_poverty_estimate_3usd_2021_ppp_gni_source_indicator",
    "gameplay_poverty_estimate_3usd_2021_ppp_confidence",
    "gameplay_poverty_estimate_3usd_2021_ppp_source_urls",
    "gameplay_poverty_estimate_3usd_2021_ppp_source_note",
)


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def _number(value: str | int | float | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Expected finite number, got {value!r}")
    return number


def _read_gni_ppp(path: Path) -> dict[str, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or len(payload) != 2:
        raise ValueError(f"Unexpected World Bank response shape: {path}")
    observations = payload[1]
    if not isinstance(observations, list):
        raise ValueError(f"World Bank response has no observation list: {path}")
    values: dict[str, float] = {}
    for observation in observations:
        if str(observation.get("date") or "") != "2001":
            continue
        country_id = str(observation.get("countryiso3code") or "").upper()
        value = _number(observation.get("value"))
        if country_id and value is not None and value > 0:
            values[country_id] = value
    return values


def _read_hdi_quality(path: Path) -> dict[str, str]:
    quality: dict[str, str] = {}
    for row in _read_tsv(path):
        country_id = row["id"].strip().upper()
        status = row.get("status", "").strip()
        quality[country_id] = status or "backfill"
    return quality


def _feature_rows(
    country_ids: list[str],
    demographics_path: Path,
    hdi_backfills_path: Path,
    gni_source_path: Path,
) -> dict[str, dict]:
    demographics = {
        row["id"].strip().upper(): row for row in _read_tsv(demographics_path)
    }
    hdi_quality = _read_hdi_quality(hdi_backfills_path)
    gni_values = _read_gni_ppp(gni_source_path)
    features = {}
    for country_id in country_ids:
        if country_id in hdi_quality and hdi_quality[country_id] in {
            "not_applicable",
            "not_reported",
        }:
            hdi = None
            quality = hdi_quality[country_id]
        else:
            demographic_row = demographics.get(country_id, {})
            hdi = _number(demographic_row.get("human_dev"))
            if country_id in hdi_quality:
                quality = hdi_quality[country_id]
            else:
                quality = "UNDP HDR 2025 retrospective series"
        gni = gni_values.get(country_id)
        features[country_id] = {
            "hdi": hdi,
            "hdi_quality": quality,
            "gni": gni,
        }
    return features


def _weighted_knn(
    target: dict,
    training: list[dict],
    *,
    neighbor_count: int = NEIGHBOR_COUNT,
) -> tuple[float, list[tuple[str, float]]]:
    usable_features = ["hdi"]
    if target.get("gni") is not None:
        usable_features.append("log_gni")

    for row in training:
        row["log_gni"] = math.log10(row["gni"])

    scales = {
        feature: statistics.pstdev(row[feature] for row in training) or 1.0
        for feature in usable_features
    }

    target_values = {
        "hdi": target["hdi"],
        "log_gni": math.log10(target["gni"]) if target.get("gni") else None,
    }
    distances = []
    for row in training:
        distance = math.sqrt(
            sum(
                ((target_values[feature] - row[feature]) / scales[feature]) ** 2
                for feature in usable_features
            )
        )
        distances.append((row["id"], row["value"], distance))
    nearest = sorted(distances, key=lambda item: (item[2], item[0]))[
        : min(neighbor_count, len(distances))
    ]
    weighted_sum = 0.0
    total_weight = 0.0
    for _, value, distance in nearest:
        weight = 1 / ((distance + DISTANCE_OFFSET) ** 2)
        weighted_sum += value * weight
        total_weight += weight
    estimate = min(100.0, max(0.0, weighted_sum / total_weight))
    return estimate, [(country_id, distance) for country_id, _, distance in nearest]


def generate_rows(
    *,
    countries_path: Path = COUNTRIES_PATH,
    demographics_path: Path = DEMOGRAPHICS_PATH,
    pip_path: Path = PIP_PATH,
    hdi_backfills_path: Path = HDI_BACKFILLS_PATH,
    gni_source_path: Path = GNI_SOURCE_PATH,
) -> list[dict[str, str]]:
    countries = _read_tsv(countries_path)
    country_ids = [row["id"].strip().upper() for row in countries]
    if not country_ids or len(country_ids) != len(set(country_ids)):
        raise ValueError("Country roster is empty or contains duplicate IDs")

    pip_rows = {row["id"].strip().upper(): row for row in _read_tsv(pip_path)}
    if set(pip_rows) != set(country_ids):
        raise ValueError("PIP table does not match the game-country roster")
    observed_ids = {
        country_id
        for country_id, row in pip_rows.items()
        if row.get(PIP_AVAILABLE, "").lower() == "true"
        and _number(row.get(PIP_VALUE)) is not None
    }
    features = _feature_rows(
        country_ids, demographics_path, hdi_backfills_path, gni_source_path
    )

    training = []
    for country_id in sorted(observed_ids):
        feature = features[country_id]
        if feature["hdi"] is None or feature["gni"] is None:
            raise ValueError(f"PIP training row lacks model inputs: {country_id}")
        survey_year = _number(pip_rows[country_id].get(PIP_SURVEY_YEAR))
        if survey_year is None or not 2001 <= survey_year < 2002:
            raise ValueError(f"PIP training row is not a 2001 survey: {country_id}")
        training.append(
            {
                "id": country_id,
                "hdi": feature["hdi"],
                "gni": feature["gni"],
                "value": _number(pip_rows[country_id].get(PIP_VALUE)),
            }
        )
    if len(training) < NEIGHBOR_COUNT:
        raise ValueError("Insufficient exact-year PIP training observations")

    gni_source_sha256 = hashlib.sha256(gni_source_path.read_bytes()).hexdigest()
    source_urls = " | ".join(
        (
            f"{PIP_API_URL}?country=all&year=2001&fill_gaps=FALSE&version={PIP_SOURCE_VERSION}",
            GNI_API_URL,
            HDI_SOURCE_URL,
        )
    )
    output = []
    for country_id in country_ids:
        if country_id in observed_ids:
            continue
        feature = features[country_id]
        hdi = feature["hdi"]
        if hdi is None:
            output.append(
                {
                    "id": country_id,
                    "gameplay_poverty_estimate_3usd_2021_ppp_pct": "",
                    "gameplay_poverty_estimate_3usd_2021_ppp_pct_available": "false",
                    "gameplay_poverty_estimate_3usd_2021_ppp_scenario_year": "2001",
                    "gameplay_poverty_estimate_3usd_2021_ppp_line_usd_per_person_per_day": "3",
                    "gameplay_poverty_estimate_3usd_2021_ppp_line_ppp_year": "2021",
                    "gameplay_poverty_estimate_3usd_2021_ppp_type": "not_estimated",
                    "gameplay_poverty_estimate_3usd_2021_ppp_method": "No applicable or reported HDI input; no estimate generated.",
                    "gameplay_poverty_estimate_3usd_2021_ppp_training_observation_count": str(
                        len(training)
                    ),
                    "gameplay_poverty_estimate_3usd_2021_ppp_nearest_training_ids": "",
                    "gameplay_poverty_estimate_3usd_2021_ppp_nearest_training_distance": "",
                    "gameplay_poverty_estimate_3usd_2021_ppp_hdi_input_2001": "",
                    "gameplay_poverty_estimate_3usd_2021_ppp_hdi_input_quality": feature[
                        "hdi_quality"
                    ],
                    "gameplay_poverty_estimate_3usd_2021_ppp_gni_per_capita_ppp_current_intl_dollars_2001": (
                        f"{feature['gni']:.6f}" if feature["gni"] is not None else ""
                    ),
                    "gameplay_poverty_estimate_3usd_2021_ppp_gni_source_indicator": GNI_INDICATOR,
                    "gameplay_poverty_estimate_3usd_2021_ppp_confidence": "not_applicable"
                    if feature["hdi_quality"] == "not_applicable"
                    else "none",
                    "gameplay_poverty_estimate_3usd_2021_ppp_source_urls": source_urls,
                    "gameplay_poverty_estimate_3usd_2021_ppp_source_note": (
                        "PIP national household survey data do not apply or the 2001 HDI input is unavailable; "
                        "the neutral simulation fallback is not used as evidence. "
                        f"WDI GNI snapshot SHA-256: {gni_source_sha256}."
                    ),
                }
            )
            continue

        estimate, nearest = _weighted_knn(feature, training)
        quality_status = feature["hdi_quality"]
        low_quality_hdi = quality_status in {
            "calculated_estimate",
            "national_report_proxy",
            "regional_estimate_proxy",
            "territory_proxy",
        }
        confidence = (
            "low" if feature["gni"] is not None and not low_quality_hdi else "very_low"
        )
        output.append(
            {
                "id": country_id,
                "gameplay_poverty_estimate_3usd_2021_ppp_pct": f"{estimate:.4f}",
                "gameplay_poverty_estimate_3usd_2021_ppp_pct_available": "true",
                "gameplay_poverty_estimate_3usd_2021_ppp_scenario_year": "2001",
                "gameplay_poverty_estimate_3usd_2021_ppp_line_usd_per_person_per_day": "3",
                "gameplay_poverty_estimate_3usd_2021_ppp_line_ppp_year": "2021",
                "gameplay_poverty_estimate_3usd_2021_ppp_type": "gameplay_model",
                "gameplay_poverty_estimate_3usd_2021_ppp_method": (
                    "Inverse-distance-weighted mean of five nearest exact-2001 PIP survey "
                    "observations in standardized HDI and log10 GNI-per-capita PPP space; "
                    "HDI-only distance when 2001 GNI PPP is unavailable."
                ),
                "gameplay_poverty_estimate_3usd_2021_ppp_training_observation_count": str(
                    len(training)
                ),
                "gameplay_poverty_estimate_3usd_2021_ppp_nearest_training_ids": ",".join(
                    country_id for country_id, _ in nearest
                ),
                "gameplay_poverty_estimate_3usd_2021_ppp_nearest_training_distance": ",".join(
                    f"{distance:.6f}" for _, distance in nearest
                ),
                "gameplay_poverty_estimate_3usd_2021_ppp_hdi_input_2001": f"{hdi:.6f}",
                "gameplay_poverty_estimate_3usd_2021_ppp_hdi_input_quality": quality_status,
                "gameplay_poverty_estimate_3usd_2021_ppp_gni_per_capita_ppp_current_intl_dollars_2001": (
                    f"{feature['gni']:.6f}" if feature["gni"] is not None else ""
                ),
                "gameplay_poverty_estimate_3usd_2021_ppp_gni_source_indicator": GNI_INDICATOR,
                "gameplay_poverty_estimate_3usd_2021_ppp_confidence": confidence,
                "gameplay_poverty_estimate_3usd_2021_ppp_source_urls": source_urls,
                "gameplay_poverty_estimate_3usd_2021_ppp_source_note": (
                    "Scenario-only model output for the World Bank PIP $3/day (2021 PPP) international-line "
                    "metric. It is not a national poverty-line observation, survey result, or historical "
                    "2001 publication. Inputs are the 2001 HDI scenario value and exact-year WDI GNI per-capita "
                    "PPP when available. "
                    f"WDI GNI snapshot SHA-256: {gni_source_sha256}."
                ),
            }
        )
    return output


def render_tsv(rows: list[dict[str, str]]) -> str:
    from io import StringIO

    buffer = StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=OUTPUT_COLUMNS,
        delimiter="\t",
        lineterminator="\n",
        extrasaction="raise",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Verify output without rewriting it"
    )
    args = parser.parse_args()
    rows = generate_rows()
    rendered = render_tsv(rows)
    if args.check:
        current = OUTPUT_PATH.read_text(encoding="utf-8")
        if current != rendered:
            raise SystemExit(f"Generated estimate table is stale: {OUTPUT_PATH}")
        print(f"Verified {OUTPUT_PATH}")
        return 0
    OUTPUT_PATH.write_text(rendered, encoding="utf-8", newline="")
    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
