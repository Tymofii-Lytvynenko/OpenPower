# Gameplay poverty scenario estimates for 2001

## Purpose and scope

`countries_poverty_scenario_estimates_2001.tsv` adds a gameplay-only estimate for countries without an exact 2001 survey in the separate World Bank PIP `$3/day (2021 PPP)` series. It does **not** fill or replace the country-specific national-poverty-line field. National lines differ by country and remain unavailable where no compatible observation was found.

The table has 153 rows: 151 modeled estimates and two rows without an estimate. The two excluded cases are Antarctica, where a national household poverty measure is not applicable, and Vatican City, for which no historical HDI value was reported. OpenPower's neutral simulation HDI fallback is not treated as evidence. The 46 observed 2001 PIP records remain unchanged in `countries_poverty_international_2001.tsv`.

## Reproducible model

The target metric is the PIP national-survey headcount below `$3 per person per day` in 2021 PPP. The model is calibrated only on the 46 exact-2001 survey observations in the archived PIP response; alternate welfare measures from the same survey remain outside the training set.

For each missing country, the generator finds the five training countries nearest in standardized feature space. Features are the country's 2001 HDI value and the base-10 logarithm of its World Bank 2001 GNI per-capita PPP in current international dollars. Each feature is centered and scaled by the population standard deviation of the 46 training rows. The estimate is an inverse-distance weighted mean with weight `1 / (distance + 0.25)^2`, clamped to 0–100 percent. If the WDI PPP input is missing, distance uses HDI alone and the confidence is `very_low`. Estimates that use proxy or modeled HDI inputs are also `very_low`; other two-input estimates are `low`.

This nearest-neighbor output is a scenario proxy, not a survey result, confidence interval, or national-line rate. It applies a modern 2021 PPP line retrospectively to the 2001 scenario, and should be labeled accordingly in any interface.

## Source inputs

- World Bank Poverty and Inequality Platform PIP version `20260922_2021_01_02_PROD`; exact-year national household surveys and the `$3/day (2021 PPP)` line. See `pip_2021_ppp_3usd_2001.json` and `pip_2021_ppp_3usd_2001.tsv`.
- World Bank WDI `NY.GNP.PCAP.PP.CD`, observation year 2001, current international dollars. Snapshot: `NY.GNP.PCAP.PP.CD_2001.json`; SHA-256 is embedded in each generated row.
- UNDP HDR 2025 retrospective HDI series as used by the 2001 scenario, with existing source-quality statuses from `hdi_backfills_2001.tsv`.

Regenerate the table with:

```powershell
python utils/generate_poverty_scenario_estimates_2001.py
```

Verify it without rewriting the table with:

```powershell
python utils/generate_poverty_scenario_estimates_2001.py --check
```
