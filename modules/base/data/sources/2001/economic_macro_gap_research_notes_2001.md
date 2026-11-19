# Research notes: remaining macroeconomic gaps

This file records additional source leads found while reviewing cells still blank in the 2001 macroeconomic series. Numeric observations suitable for separate, dated country extensions are in `economic_supplement_2001.tsv` and `economic_reported_observations_2001.tsv`. They retain the actual source year and definition. They must not be copied into the modeled WDI/ILO or IMF WEO fields.

## Additional observations recorded

- **San Marino CPI:** the 2001 IMF Article IV table reports 3.3% annual-average inflation for 2001, marked as an IMF staff estimate. The country extension retains it under a separate field.
- **Afghanistan CPI:** the IMF Article IV report lists a Kabul CPI year-on-year estimate of -43.4% for fiscal year 2001/02. It is not a national calendar-year rate; it is kept separate and explicitly fiscal-year dated.
- **Seychelles unemployment:** the Central Bank of Seychelles' 2005 annual report gives 4.4% at end-2001. The report attributes the calculation to the Employment Division.
- **Federated States of Micronesia unemployment:** the FSM Information Service's 2003 release of the 2000 census reports 22% nationally.
- **Kiribati unemployment:** the Government of Kiribati's 2007 MDG report gives 1.6% in the 2000 census. It explains that subsistence and informal work complicate the unemployment definition; the separate 78.1% measure that treats village workers and self-employed people as unemployed is deliberately excluded.
- **Palau unemployment:** the Palau government census series reports 2.3% for 2000 among residents aged 16 and over.
- **Marshall Islands unemployment:** the 1999 census series, summarized in the RMI Statistical Yearbook 2002, reports 30.9%. The two-year gap from the scenario date is retained.
- **Nauru unemployment:** the 2002 census reports 22.7% among residents aged 16 and over. This is one year after the scenario date.
- **Tuvalu unemployment:** the 2002 census reports 6.5% among residents aged 15 and over. This is one year after the scenario date.
- **Marshall Islands CPI:** the IMF's 2005 Article IV table reports 1.8% consumer-price change for FY2001, a fiscal year ending September 30, based on authority data and IMF staff estimates. A contemporaneous 2001 IMF notice described Majuro-based CPI inflation as below 1% without a precise rate; the later figure is retained with that revision conflict disclosed.
- **Liechtenstein unemployment:** the official yearbook reports 354 registered wholly unemployed people and a 1.2% rate at year-end 2001, defined as a share of employees. It is not a labor-force modeled ILO estimate.
- **Monaco unemployment:** the government's 2004 report to the UN gives 2.45% on 1 January 2001. Its job-seeker group includes Monaco residents and people who previously worked in Monaco but live in neighbouring French communes or are Italian cross-border workers; the value is a labour-market catchment measure, not a resident-only rate.
- **San Marino unemployment:** the official health profile reports a 2.92% annual-average total rate for 2001. It separately reports a 1.21% strict-unemployment measure; the source extension stores the total rate and names the alternative in the note.

## Gaps that remain unresolved

- **GDP and GDP per capita:** PRK now has a separate UNdata SNAAMA estimate in `economic_supplement_2001.tsv`; it is not duplicated here. ATA has no resident national economy. SSD was part of Sudan in 2001 and has no separate contemporaneous national accounts. VAT does not publish a comparable national-accounts GDP series. No distinct country GDP estimate was found for those remaining IDs.
- **CPI:** the CIA Factbook 2001 edition reports Nauru's -3.6% estimate for 1993, not 2001. The Marshall Islands now has a later retrospective 1.8% FY2001 estimate, while the contemporaneous IMF notice says below 1%; the value remains a separately labeled fiscal-year estimate with the discrepancy visible. Somalia's FAO/FSNAU historical material provides geographically and basket-specific food/minimum-expenditure series; these are not a national all-items CPI. The accessible DPRK estimates are small commodity-basket reconstructions rather than a comparable official CPI. Monaco's later official statistical series cites French CPI and starts its published annual table in 2004. These were not relabeled as 2001 national CPI values.
- **Inflation in ATA, SSD, and VAT:** these are not comparable independent national consumer-price economies in 2001. No numeric zeros are inferred.

## Disposition of remaining core-series gaps

The core WDI/ILO/WEO coverage remains unchanged. Every core blank that represents a playable country is addressed by a separately labeled reported observation, compatible alternative, or gameplay proxy; Antarctica is explicitly not applicable. These sidecars do not increase the comparable core-series counts or make unlike definitions interchangeable.

- **GDP and GDP per capita (4 core gaps each):** ATA is not applicable; PRK has a separate UNdata SNAAMA observation in `economic_supplement_2001.tsv`; SSD and VAT have very-low-confidence gameplay proxies in `economic_gameplay_proxy_ledger_2001.tsv`. The SSD proxy applies Sudan's national average to a territory that was part of Sudan in 2001. The Vatican proxy uses Italy's GDP per capita and the separate 2001 population scenario input; neither proxy is a country national-accounts observation.
- **CPI (12 core gaps):** ATA is not applicable. Calendar-year or period-specific source alternatives are recorded for AFG (Kabul, FY2001/02), AND, CUB, MHL, and SMR (IMF staff estimate). Low/very-low-confidence gameplay proxies are recorded for MCO, NRU, PRK, SOM, SSD, and VAT. They are not national CPI observations for the target countries.
- **Unemployment (19 core gaps):** ATA is not applicable. Dated national, census, or labor-market alternatives are recorded for ATG, CUB, DMA, FSM, GRD, KIR, KNA, KOS, LIE, MCO, MHL, NRU, PLW, SMR, SYC, TUV, and TWN; their actual years, population definitions, and source scopes remain in the supplemental ledgers. AND has only an undated Factbook scenario prior, and VAT has an Italy-based gameplay proxy. Neither is a measured 2001 ILO rate.

## Source URLs

- IMF San Marino Article IV (2001): <https://www.imf.org/external/pubs/ft/scr/2001/cr01225.pdf>
- IMF Afghanistan Article IV: <https://www.elibrary.imf.org/view/journals/002/2005/033/article-A003-en.xml>
- Central Bank of Seychelles Annual Report 2005: <https://www.cbs.sc/Downloads/publications/Annual%20Report%202005.pdf>
- FSM Information Service, 2000 census release: <https://www.fsmgov.org/press/pr05300b.htm>
- Government of Kiribati MDG Report 2007: <https://psro.dataforall.org/sites/default/files/2024-10/Kiribati_mdg_2007.pdf>
- Palau government labor-market statistics: <https://www.palaugov.pw/executive-branch/ministries/finance/budgetandplanning/labor-market-statistics/>
- RMI Statistical Yearbook 2002: <https://marshall.csu.edu.au/Marshalls/html/STATS/RMIYearbook2002.pdf>
- Nauru 2002 Census Main Report: <https://psro.dataforall.org/sites/default/files/2024-10/Nauru_1992_2002_Census_Report_and_Demographic_profile_Part%201.pdf>
- Tuvalu Census 2002, Volume 1: <https://www.fao.org/fileadmin/templates/ess/ess_test_folder/World_Census_Agriculture/Country_info_2000/Reports_2/TUV_ENG_REP1_2002.pdf>
- Liechtenstein in Zahlen 2002: <https://archiv.llv.li/files/as/Liechtenstein_in_Zahlen_2002.pdf>
- Monaco initial report to the UN Committee on Economic, Social and Cultural Rights, E/1990/5/Add.64: <https://docstore.ohchr.org/SelfServices/FilesHandler.ashx?enc=FjRM9mPKgJVtNKVqL41Ne9KBgHLHeQAGhmpfQUBxDZ/HD3jC5LPYk8q9bPJP2y7Oj3vVckxcAOBe2P21mY58uA%3D%3D>
- IMF Republic of the Marshall Islands 2005 Article IV report: <https://www.imf.org/external/pubs/ft/scr/2006/cr0695.pdf>
- San Marino Health Authority, Il Profilo di Salute della Repubblica di San Marino: <https://www.gov.sm/pub2/GovSM/dam/jcr%3A40d55b9b-ccaf-4a31-aafe-71ba88103ea7/285file_1_1123.pdf>
