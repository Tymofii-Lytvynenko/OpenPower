# Separately defined development indicators

The generated `development_supplement_2001.tsv` ledger and
`countries_development_supplement_2001.tsv` country extension add sourced
values only where the matching UNDP 2001 baseline field is unavailable. They do
not overwrite the UNDP series because the definitions or reference years differ.

| Field | Coverage of previously missing UNDP values | Observation and scope |
|---|---:|---|
| `historical_school_life_expectancy_wdi_years_2001` | 3/16 | World Bank WDI `SE.SCH.LIFE`, 2001; school life expectancy from primary through tertiary, both sexes. It is kept separate from UNDP expected years of schooling. |
| `historical_gni_per_capita_wdi_ppp_current_intl_dollars_2001` | 3/10 | World Bank WDI `NY.GNP.PCAP.PP.CD`, 2001; current international-dollar PPP. It is kept separate from UNDP's 2021 PPP-dollar measure. |
| `historical_mean_schooling_barrolee_years_population_15plus_2000` | 1/21 | Barro-Lee 2013 retrospective estimate for 2000; average years attained by the population aged 15 and over, both sexes. This differs from the UNDP mean-schooling population scope and is one year earlier. |
| `historical_mean_schooling_barrolee_years_population_25plus_2000` | 1/21 | Barro-Lee 2013 retrospective estimate for 2000; average years attained by the population aged 25 and over, both sexes. Its age threshold matches the UNDP mean-schooling scope, while its source series and observation year remain distinct. |

The exact added country IDs are KIR, MDA, and SYC for school life expectancy;
NRU, PRI, and SDN for current-PPP GNI per capita; and TWN for both Barro-Lee
2000 population-age variants. Every row retains its source URL, observation
year, scope, note, and source-file SHA-256. Availability flags distinguish absent
observations from a measured zero. The two Taiwan Barro-Lee fields are separate
because the 15+ and 25+ populations have different averages.

The World Bank responses are archived as `SE.SCH.LIFE_2001.json` and
`NY.GNP.PCAP.PP.CD_2001.json`. The Barro-Lee 15+ and 25+ downloads are read
during regeneration; their URLs and SHA-256 hashes are recorded in the manifest
without bundling the full datasets. The manifest also records retrieval time and
coverage.
Regenerate the country extension and ledger with:

```powershell
.\.venv\Scripts\python.exe utils/import_development_supplement_2001.py
```

Sources:

- World Bank WDI `SE.SCH.LIFE`: https://api.worldbank.org/v2/country/all/indicator/SE.SCH.LIFE?date=2001&format=json&per_page=1000
- World Bank WDI `NY.GNP.PCAP.PP.CD`: https://api.worldbank.org/v2/country/all/indicator/NY.GNP.PCAP.PP.CD?date=2001&format=json&per_page=1000
- Barro and Lee, 2013, *A New Data Set of Educational Attainment in the World, 1950–2010*: https://barrolee.github.io/BarroLeeDataSet/
- Barro-Lee variable definitions: https://barrolee.github.io/BarroLeeDataSet/Aboutdataset/Def.html
- Barro-Lee 25+ educational attainment data: https://barrolee.github.io/BarroLeeDataSet/BLData/BL2013_MF2599_v2.2.csv
