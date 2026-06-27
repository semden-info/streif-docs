# Streif — Spike 1 (рендер): data pipeline

Чорнові артефакти для **Spike 1** (`docs/11-spike-plan.md`). Мета — реальні дані Volda → `buildings.pmtiles` для тесту двошарового рендеру. Код одноразовий.

## `build_volda_tiles.py`
Геометрія (INSPIRE Core2d, WFS) + тип (Matrikkelen-Bygningspunkt, WFS) → join → GeoJSON → PMTiles, зі стабільним `building_id` і колірною групою `type`.

### Передумови
```
pip install geopandas requests
# + у PATH: ogr2ogr (GDAL), tippecanoe (felt/tippecanoe ≥ 2.17)
```

### Запуск
```
python3 build_volda_tiles.py
```
Вихід: `buildings.geojson`, `buildings.pmtiles` (бандлити в каркас-застосунок як `pmtiles://asset://buildings.pmtiles`).

### Звірити на ПЕРШОМУ запуску (Geonorge треба перевіряти наживо)
1. **Назви шарів/полів WFS** — скрипт друкує доступні колонки. Якщо `bygningstype` / `bygningsnummer` / шар `Bygning` названі інакше — підправ `TYPE_FIELD` / `ID_FIELD` / `MATRIKKEL_LAYER`. Швидка розвідка:
   ```
   ogrinfo -so "WFS:https://wfs.geonorge.no/skwms1/wfs.matrikkelen-bygningspunkt"
   ```
2. **Повнота** — WFS має ліміт к-сті фіч і ~10–15 хв затримку. Volda ~12k будинків; якщо вийшло помітно менше — перейди на per-kommune файли `nedlasting.geonorge.no` (`06` §3).
3. **Колірна мапа** `classify()` — наближена; уточнити за SSB Klass 31 / `building_types.csv`.
4. **Ліцензія** — для dogfood ок; перед публічним релізом підтвердити footprint-ліцензію з Kartverket (`DECISIONS.md` P4).

> Якщо WFS капризує — `building2osm` лишається референсом логіки join і таблиці типів (його WFS-шлях зламаний, тож файли тягнемо напряму).
