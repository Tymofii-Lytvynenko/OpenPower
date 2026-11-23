# Economy gameplay parameters for the 2001 start

`internal_tax_rate` and `industrial_growth_rate` are gameplay priors, not measured historical series. They make country starts respond to the country-specific inputs already present in the base data:

- `internal_tax_rate = (global_tax_rate + personal_income_tax_rate) / 2`.
- `industrial_growth_rate = 0.01 + 0.03 * (1 - human_dev)`, using `human_dev` from `countries_dem.tsv`. This catch-up prior gives lower-development economies more organic growth; rates are annual fractions.

`security_upkeep` and `diplomacy_upkeep` remain `0.0` because the bundled sources do not provide comparable country-level annual expenditure for either service. Zero here means the baseline is not modeled, not that historical expenditure was zero. Military-unit upkeep and treaty maintenance remain separate modeled costs. Replace these defaults only when comparable source data is added.
