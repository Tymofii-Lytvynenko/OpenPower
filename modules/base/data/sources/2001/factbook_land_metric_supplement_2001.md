# CIA Factbook land-metric supplements

`factbook_land_metric_supplement_2001.tsv` contains selected CIA Factbook
land-use and area values used only when the corresponding historical field is
blank. The scenario year is 2001; each row retains the actual estimate year
when the Factbook states one.

## Kosovo forest estimate

The CIA World Factbook 2018 Kosovo entry reports forest at **41.7%** and marks
the value `(2001 est.)`. The imported row uses observation year 2001 and keeps
the publication year 2018. The value is rounded and the Factbook does not
describe its estimation method, so it is a retrospective CIA estimate rather
than a harmonized WDI/FAOSTAT observation.

The value is scoped to Kosovo as named in the CIA entry. The game Serbia area
includes Kosovo, and this estimate does not split Kosovo out of Serbia's land
or forest aggregates. It fills only the otherwise blank KOS forest percentage;
it adds no land-area value.

Sources:

- CIA, *The World Factbook 2018*, Kosovo, “Land use”:
  <https://johnmeister.com/FACTS/WORLD-FACTBOOK-2018/geos/kv.html>
- Archived Factbook edition transcription and history:
  <https://www.thefactbook.org/kosovo/2018>

Regenerate the historical country table with:

```powershell
.venv\Scripts\python.exe utils/import_historical_country_data.py
```
