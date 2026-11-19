# National poverty gap audit for 2001

## Scope and result

The primary country-history table had 100 blank `historical_poverty_rate_pct` values across 199 country rows when this audit began. The primary series currently combines dated CIA Factbook national estimates and World Bank national-poverty-line observations. The separate PIP `$3/day (2021 PPP)` survey series is not a national poverty line and was excluded from this review.

I queried the World Bank `SI.POV.NAHC` national-poverty-line indicator for its full available historical range through 2001 (`1960:2001`). The API returned 99 non-null observations for 39 country codes; intersection with the 100 blank primary IDs produced three new records with country-level support for the year, national line, welfare measure, scope, and method. These are stored in [`countries_poverty_national_supplement_2001.tsv`](../../countries/countries_poverty_national_supplement_2001.tsv) and should be reviewed for later integration into the primary series:

A targeted review of primary statistical-office and World Bank poverty-assessment sources for additional gaps found four more qualified survey observations: BIH (2001 LSMS), CIV (2002 ENV), FJI (2002/03 HIES), and SEN (2001/02 ESAM-II). All remain separate national-line records, and their survey years are preserved as reported.

| ID | Rate | Survey period | Line and method |
| --- | ---: | --- | --- |
| ETH | 44.2% | 1999/2000 | Government cost-of-basic-needs line; 2,200 kcal/adult-equivalent basket plus non-food allowance; national consumption headcount. |
| NAM | 69.3% | 1993/94 | NSA upper-bound national line; N$145.88/month in 1993/94 prices; individual headcount from adjusted per-capita expenditure. |
| SWZ | 69.0% | 2000/01 | National basic-needs line; minimum expenditure for basic human needs, E128.60/capita/month; SHIES headcount. |
| BIH | 19.5% | 26 Sep–23 Nov 2001 | General/absolute line of KM 2,198 per person/year at average BiH prices; per-capita total consumption headcount; 95% interval ±3.6 percentage points. The nationally reported LSMS sample covered FBiH and RS; Brčko was excluded from the sampling frame. |
| CIV | 38.4% | 2002 ENV | Relative national monetary line of FCFA 183,450 per person/year; per-capita household-consumption headcount. National results cover urban and rural strata and are reported by five strata. |
| FJI | 34.4% | 2002/03 HIES | Government-reported Basic Needs Poverty Line (food plus non-food; F$155 per household/week); per-adult-equivalent income headcount. The current Fiji Bureau of Statistics table rounds the value to 35%; a later World Bank re-estimation gives 39.8% under a different analysis, so estimates are not merged. |
| SEN | 57.1% | 2001/02 ESAM-II | National cost-of-basic-needs line: 2,400-kcal adult-equivalent food basket plus locality-specific non-food allowance; person headcount from household expenditure. Official results cover Dakar, other urban, and rural areas. |

The World Bank API labels the observations 1999, 1993, and 2000 respectively; the country reports identify the actual survey periods shown above. Preserve both fields. Do not recast these as 2001 surveys. The national lines are country-specific and therefore not suitable for cross-country welfare comparisons.

## Official but non-fillable alternative

UNDP's 2003 Human Development Report table 3 lists Cuba at 41.9% below its national income poverty line. The report gives only a latest-observation window of 1987–2000 for this column and does not identify Cuba's actual survey year, welfare measure, row-level coverage, or estimation method. This record is preserved in [`national_poverty_alternatives_2001.tsv`](national_poverty_alternatives_2001.tsv), clearly marked ineligible for the year-specific primary field.

The report's reader's guide describes national lines generally as authority-defined and household-survey-based, while noting that their definitions differ across countries. That general note does not fill the missing Cuba row metadata.

## Remaining gaps

Seven qualified survey observations cover 7 of the 100 currently blank primary IDs. Because these records remain separate alternatives, the primary table is unchanged at 99/199; combined primary-plus-supplement display coverage is 106/199, with 93 IDs still lacking any national-line observation in these tables. The Cuba entry does **not** close a gap because its survey year and welfare metadata are missing. The targeted source check also reviewed Eritrea and Gambia: Eritrea's detailed LSMS headcount is from 2003, while the relevant Gambian national household-poverty observations are from 1998 and 2003/04, outside the 1999–2002 window. Guinea-Bissau's 2002 ILAP results report $1/$2 per-day thresholds at 1985 PPP per adult equivalent rather than the country-specific national poverty line used by this supplement, so they are not treated as a national-line alternative. No other year-specific national-line observation meeting the metadata standard was found in the reviewed full-history WDI series, relevant UNDP HDR 2003 tables, or this bounded source follow-up. This is a bounded source review, not a claim that no national statistics exist.

The remaining IDs after setting aside the seven documented candidates are (CUB remains blank in the primary series despite its alternative record):

`AFG, AGO, AND, ARE, ATA, ATG, AUS, AUT, BFA, BHR, BHS, BRB, BRN, BTN, CAF, CAN, CHE, COD, COG, COM, CUB, CYP, CZE, DEU, DJI, DMA, DNK, ERI, ESP, FIN, FRA, FSM, GAB, GMB, GNQ, GRC, GRD, GUY, IRQ, ISL, ISR, ITA, JPN, KIR, KNA, KOR, KOS, KWT, LBY, LCA, LIE, LTU, LUX, LVA, MCO, MDV, MHL, MLI, MLT, MNE, NLD, NOR, NRU, NZL, OMN, PLW, PRK, PRT, PSE, QAT, SAU, SDN, SGP, SLB, SMR, SOM, SRB, SSD, STP, SUR, SVK, SVN, SWE, SYC, TON, TUR, TUV, URY, VAT, VCT, VUT, WSM, PRI`.


## Sources consulted

- [World Bank API: Poverty headcount ratio at national poverty lines](https://api.worldbank.org/v2/country/all/indicator/SI.POV.NAHC?date=1960%3A2001&format=json&per_page=20000)
- [World Bank, Federal Democratic Republic of Ethiopia PRSP and Joint IDA-IMF Staff Assessment](https://documents1.worldbank.org/curated/en/683561468773953737/pdf/multi0page.pdf)
- [Namibia Statistics Agency, Poverty Dynamics in Namibia](https://cms.my.na/assets/documents/p19dnar71kanl1vfo14gu5rpbkq1.pdf)
- [World Bank, Swaziland: Selected Issues and Statistical Appendix](https://documents.worldbank.org/curated/en/484331468130827039/pdf/353181SW0Main0Vol.pdf)
- [World Bank and BiH statistical agencies, Bosnia and Herzegovina Poverty Assessment, Report No. 25343-BIH](https://documents1.worldbank.org/curated/en/511721468769462746/pdf/25343.pdf) — reports the line, per-capita consumption measure, national headcount, survey dates, and precision interval.
- [World Bank microdata catalog, BiH LSMS 2001](https://microdata.worldbank.org/index.php/catalog/65/study-description) — documents that Brčko was excluded from the sampling frame.
- [Institut National de la Statistique / CLCP, Côte d'Ivoire ENV 2002 catalog](https://nada.anstat.ci/index.php/catalog/19) — identifies the 2002 household living-standards survey and its national poverty result.
- [Fiji state report to CEDAW (2009)](https://digitallibrary.un.org/record/683003/files/CEDAW_C_FJI_2-4-EN.pdf) — records the 34.4% 2002/03 HIES headcount and defines the BNPL as food plus non-food components; the current Fiji Bureau of Statistics series rounds this result to 35%.
- [Fiji Bureau of Statistics, Poverty Indicators](https://www.statsfiji.gov.fj/statistics/social-statistics/poverty-indicators/) — gives the official rounded 2002/03 national, urban, and rural HIES results.
- [Pacific Economic Bulletin, “50/50 by 2020: Poverty and Redistributive Politics in Post-independence Fiji”](https://devpolicy.org/PEB-APPS/PEB%202007-2010/PEB22_2_50_by_2020__poverty_and_2007.pdf) — identifies 34.4% as the population share with adult-equivalent per-capita income below BNPL, citing the HIES analysis prepared for UNDP.
- [Fiji Bureau of Statistics HIES survey metadata](https://catalog.ihsn.org/catalog/1522) — identifies the national 2002/03 survey and its national geographic coverage.
- [Senegal DPS, ESAM-II 2001–2002 summary](https://www.vie-publique.sn/documents/10369/rapport-synthese-deuxieme-enquete-senegalaise-menages-esam-ii-2001-2002-dps) — confirms the survey period, 6,624 households, and urban/rural scope.
- [UN Statistics Division, ECOWAS Poverty Profile](https://unstats.un.org/unsd/publication/ecowas_poverty_profile_e.pdf) — reproduces Senegal's 2001/02 national and locality poverty rates and the cost-of-basic-needs lines, citing the 2004 DPS/World Bank report.
- [Government of Côte d'Ivoire, Strategic National Development 2007–2015](https://extranet.who.int/countryplanningcycles/sites/default/files/country_docs/Cote%20DIvoire/cote_divoire_strategic_national_de_developpement_2007-2015.pdf) — reproduces the FCFA 183,450 per-capita annual line and national, urban/rural, and five-stratum results from INS ENV.
- [World Bank / INS, Côte d'Ivoire Poverty Assessment](https://documents1.worldbank.org/curated/en/792211468245998811/pdf/366250ESW0P0830I0Poverty0Assessment.pdf) — defines the headcount by per-capita consumption below the poverty line and tabulates 1998/2002 results.
- [FAO, Eritrea 2003 Living Standards Measurement Survey poverty results](https://www.ecss-online.com/data/pdfs/food-security-strategy-eritrea.pdf) — the cited headcount is explicitly sourced to LSMS 2003, outside this audit's survey window.
- [Gambia Bureau of Statistics, Methods for Poverty Analysis](https://www.gbosdata.org/downloads-file/37-integrated-household-survey-2010) — identifies national poverty studies in 1992, 1998, and 2003; these do not provide a qualifying 1999–2002 survey observation.
- [Gambia Bureau of Statistics, national poverty headcount series](https://www.gbosdata.org/data/718-poverty/1794-poverty-rate-headcount-national) — lists national survey observations for 1998 and 2003 onward.
- [UNDP, Human Development Report 2003](https://hdr.undp.org/system/files/documents/human-development-report-2003-english.human-development-report-2003-english)
