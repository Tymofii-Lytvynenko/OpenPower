# Gameplay proxies for unresolved 2001 macroeconomic fields

## Direct-data review

`economic_indicators_2001.md` records the remaining exact-year core-field gaps: GDP and GDP per capita for ATA, PRK, SSD, and VAT; CPI for AFG, AND, ATA, CUB, MCO, MHL, NRU, PRK, SMR, SOM, SSD, and VAT; and modeled ILO unemployment for AND, ATA, ATG, DMA, FSM, GRD, KIR, KNA, KOS, LIE, MCO, MHL, NRU, PLW, SMR, SYC, TUV, TWN, and VAT.

The source review found already-recorded, separately scoped alternatives for PRK GDP/GDP per capita (UNdata SNAAMA), five CPI gaps (AFG Kabul FY2001/02, AND, CUB, MHL FY2001, and SMR), and 16 modeled-ILO unemployment gaps (national reports, census years, and other dated measures). Those remain in `economic_supplement_2001.tsv` and `economic_reported_observations_2001.tsv`; this proxy extension does not copy or replace them. The extension covers only residual gaps with no compatible separate series. No additional scope-compatible national 2001 GDP, all-items CPI, or labor-force series was found for the residual records.

## Coverage

`economic_gameplay_proxy_ledger_2001.tsv` preserves 16 long-form records: 12 numeric gameplay proxies and four explicit not-applicable Antarctica fields. The runtime extension `countries_economic_gameplay_proxies_2001.tsv` contains one wide, namespaced row for each of the eight represented country IDs so the automatic country-table join cannot multiply country rows. The numeric records cover:

- SSD and VAT GDP and GDP per capita, using Sudan and Italy 2001 WDI GDP per capita respectively, multiplied by their 2001 scenario population for GDP totals.
- MCO, NRU, PRK, SOM, SSD, and VAT CPI, using France, Australia, regional-peer medians, Sudan, and Italy as specified in each row.
- AND and VAT modeled-ILO unemployment, using the 2001 CIA Factbook's undated 0% context for Andorra and Italy's 2001 modeled-ILO rate for Vatican City.

All model rows preserve the source year and scope of the input. They are gameplay proxies only; none is an observed national series for the target country. ATA is marked unavailable/not applicable, never zero. Confidence is low for the France, Australia, Sudan, and Italy CPI comparators, and very low for the GDP, peer-median, and unemployment proxies.

## Methods and limits

- **GDP:** The proxy GDP per capita copies an exact-2001 WDI national GDP-per-capita observation from Sudan for SSD or Italy for VAT. GDP total is the proxy GDP per capita multiplied by the target's 2001 region-population sum. SSD was part of Sudan in 2001, so Sudan's national average does not measure the southern territory. Vatican City has no comparable national accounts; Italy's level cannot represent Holy See institutions or cross-border activity. Population sources and source URLs are retained per row.
- **CPI:** Single-country proxies use exact-2001 WDI CPI values. France is used for Monaco because Monaco's statistical material references French CPI; Australia is used for Nauru because the 2001 CIA Factbook lists the Australian dollar as its currency; Sudan is used for SSD; and Italy is used for VAT. PRK uses the median of China, Republic of Korea, Mongolia, and Viet Nam. Somalia uses the median of Djibouti, Ethiopia, Kenya, Sudan, and Yemen. Regional medians cannot reconstruct a national price index.
- **Unemployment:** The Andorra row retains the CIA World Factbook 2001 edition's 0% entry as an undated, very-low-confidence scenario prior; its observation year and labor-force definition are unspecified. Vatican City uses Italy's modeled ILO value only as a very-low-confidence gameplay proxy because no comparable resident labor-force series was found.
- **Antarctica:** No permanent resident national economy, consumer-price basket, or labor force exists for this 2001 scenario record, so the fields remain unavailable.

The proxies leave `countries_economic_historical.tsv` and all source-backed alternatives unchanged. Economic Health shows each proxy separately from the historical baseline, with its method, quality, scope, source note, and URLs. Regenerate or verify both the runtime extension and source ledger with:

```powershell
.\.venv\Scripts\python.exe utils/generate_economic_gameplay_proxies_2001.py
.\.venv\Scripts\python.exe utils/generate_economic_gameplay_proxies_2001.py --check
```
