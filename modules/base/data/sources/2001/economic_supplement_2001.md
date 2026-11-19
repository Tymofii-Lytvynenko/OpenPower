# 2001 economic source supplements

This manual source ledger and its generated country extension add separate, read-only series for observations dated to 2001. Fiscal-year observations retain that period in their scope note. They do not populate or override the existing WDI/IMF historical fields or live OpenPower economy state. Every row includes its source release, direct URL, unit, and scope note in `economic_supplement_2001.tsv` and the country extension provenance JSON.

## Added coverage

| Extension field | Coverage | Country IDs | Series meaning |
|---|---:|---|---|
| `historical_gdp_snaama_current_usd_2001` | 1/199 | PRK | UNSD SNAAMA GDP at current US dollars |
| `historical_gdp_per_capita_snaama_current_usd_2001` | 1/199 | PRK | UNSD SNAAMA GDP per capita at current US dollars |
| `historical_cpi_inflation_source_supplement_pct_2001` | 3/199 | AND, CUB, MHL | Official Andorra CPI decree; ECLAC Cuba December-to-December CPI; IMF Marshall Islands FY2001 estimate |
| `historical_unemployment_reported_supplement_pct_2001` | 10/199 | ATG, CUB, DMA, GRD, KNA, KOS, LIE, MCO, SMR, TWN | National, census, registered, or urban reported unemployment observations; definitions and coverage differ by source |

## Source and coverage caveats

- UNSD SNAAMA gives PRK GDP of USD 11,021,860,465 and GDP per capita of USD 476 for 2001. The database is based on official country submissions and supplements incomplete or inconsistent country-years with estimates. Its source page reports an update date of 2026-03-04. These are separate UNSD series, not replacements for missing WDI observations. [GDP record](https://data.un.org/Data.aspx?d=SNAAMA&f=grID%3A101%3BcurrID%3AUSD%3BpcFlag%3A0%3BcrID%3A408%3Byr%3A2001) · [GDP per-capita record](https://data.un.org/Data.aspx?d=SNAAMA&f=grID%3A101%3BcurrID%3AUSD%3BpcFlag%3A1%3BcrID%3A408%2C410) · [UNdata source details](https://data.un.org/DataMartInfo.aspx/_Docs/Browse.aspx?d=SNAAMA)
- Andorra's official January 16, 2002 BOPA decree states the 2001 CPI variation was 2.77%. [Official decree PDF](https://bopadocuments.blob.core.windows.net/bopa-documents/014004/pdf/25F5E.pdf)
- ECLAC's preliminary overview, published in December 2002, reports Cuba's 2001 consumer-price change as -0.5% December-to-December, based on official information. Its Cuba note limits the CPI to local-currency markets; foreign-currency prices are outside this measure. [ECLAC report](https://repositorio.cepal.org/bitstream/11362/958/1/S0211936_en.pdf)
- The IMF's later retrospective Marshall Islands table reports 1.8% consumer-price change for FY2001, based on authority data and IMF staff estimates. It defines fiscal year 2001 as ending September 30. A contemporaneous 2001 IMF notice described Majuro CPI inflation as below 1% without a precise rate; both statements remain disclosed in the source note, and this later value is not merged into the calendar-year WDI/IMF series. [IMF Country Report 06/95](https://www.imf.org/external/pubs/ft/scr/2006/cr0695.pdf)
- National reported unemployment values are ATG 8.4%, DMA 11.0%, GRD 10.2%, KNA 5.1%, KOS 57.1%, LIE 1.2% (registered unemployed as a share of employees), MCO 2.45% on 1 January (including cross-border job seekers), SMR 2.92% (annual-average total), TWN 4.57%, and Cuba urban 4.1%. Sources are the UN Statistical Yearbook 2020/2021/2025, UNdata LABORSTA census record, Liechtenstein statistical yearbook, Monaco's report to the UN Committee on Economic, Social and Cultural Rights, San Marino government report, Kosovo Agency of Statistics 2020 yearbook, Taiwan Central Bank Annual Report 2001, and ECLAC 2002 preliminary overview. Direct source URLs and release details appear on each ledger row.
- The reported unemployment field deliberately remains separate from both `historical_unemployment_modeled_ilo_pct_2001` and `historical_unemployment_imf_weo_pct_2001`. Census, national survey, and urban-rate definitions are not pooled into the modeled ILO estimate; the per-country source note identifies scope where known.

## Core-field gaps remain

These supplements do not change the main historical fields. At the time of generation, their remaining 2001 gaps are:

- GDP and GDP per capita: `ATA`, `PRK`, `SSD`, `VAT` (the PRK SNAAMA estimate above is alternate source coverage only).
- WDI/IMF CPI inflation: `AFG`, `AND`, `ATA`, `CUB`, `MCO`, `MHL`, `NRU`, `PRK`, `SMR`, `SOM`, `SSD`, `VAT` (the AND, CUB, and MHL supplements above are separate source series; they do not close the WDI/IMF field gaps).
- Modeled ILO unemployment: `AND`, `ATA`, `ATG`, `DMA`, `FSM`, `GRD`, `KIR`, `KNA`, `KOS`, `LIE`, `MCO`, `MHL`, `NRU`, `PLW`, `SMR`, `SYC`, `TUV`, `TWN`, `VAT` (the national-reported observations above do not fill the modeled ILO series).
- The IMF WEO unemployment alternate remains distinct and has 3/199 observations (`SMR`, `SYC`, `TWN`); these are not modeled ILO values.
