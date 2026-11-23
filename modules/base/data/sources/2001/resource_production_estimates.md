# 2001 resource production estimates

The base scenario allocates each country's nominal GDP across its existing OpenPower resource categories in whole US dollars. The values are gameplay estimates of contributions to GDP. Physical production statistics can inform the regional proportions.

## National totals

- Use the bundled 2001 World Development Indicators GDP where available, then the UNSD SNAAMA supplement, then the documented gameplay estimate. Antarctica retains its zero-output scenario baseline.
- Use the 2001 World Bank shares for [agriculture](https://data.worldbank.org/indicator/NV.AGR.TOTL.ZS), [industry](https://data.worldbank.org/indicator/NV.IND.TOTL.ZS), and [services](https://data.worldbank.org/indicator/NV.SRV.TOTL.ZS). Use a roster median for a missing sector and normalize the combined weights to the GDP total.
- Estimate shares inside sectors with inherited category weights and the approved Ukraine profile as a common prior. Use country-specific estimates where available. The [oil](https://data.worldbank.org/indicator/NY.GDP.PETR.RT.ZS), [gas](https://data.worldbank.org/indicator/NY.GDP.NGAS.RT.ZS), [coal](https://data.worldbank.org/indicator/NY.GDP.COAL.RT.ZS), and [mineral](https://data.worldbank.org/indicator/NY.GDP.MINR.RT.ZS) rent series provide an additional signal for extraction.
- Allocate rounding differences by largest remainder. The sum of the categories equals the GDP target to the dollar.
- The Mauritania profile assigns its iron ore to mining and keeps fossil fuels at zero for the 2001 start. Guinea and Guyana use mining categories for their ore output. [USGS on Mauritania](https://www.usgs.gov/centers/national-minerals-information-center/mauritania), [USGS on Mauritania’s first petroleum production](https://d9-wret.s3.us-west-2.amazonaws.com/assets/palladium/production/mineral-pubs/country/2006/myb3-2006-mr-ng.pdf), [USGS on Guinea](https://www.usgs.gov/centers/national-minerals-information-center/guinea), [USGS on Guyana in 2001](https://d9-wret.s3.us-west-2.amazonaws.com/assets/palladium/production/mineral-pubs/country/2001/gymyb01.pdf).

## Regional estimates

- Use country-specific production geography where available. Map coastal/offshore production to regional proxies where the game has no offshore region.
- Otherwise use the bundled 2001 population and working-age estimates, with area and biome as additional signals for agriculture and forestry. Unanchored extraction and steel use low-confidence economic-center proxies. These placements require local review.
- Use the map's unique region colors for generated records. When a source names only a shared subdivision code, use the largest map region carrying that code in the country.
- Round regional allocations by largest remainder so positive regional amounts sum to the corresponding national resource amount. Ukraine retains the approved cereal, fossil-fuel and steel amounts and allocates the remaining categories with industrial geography, population and land-use proxies. Antarctica and Redonda have zero scenario production. [Redonda land use history](https://doi.org/10.1111/1749-4877.12500)
