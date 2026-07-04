# Streif — CC-BY tile pipeline (Варіант 1, D31)

Офлайн-пайплайн: **OSM-геометрія (ODbL) + Matrikkelen-тип (CC-BY)** → статичні тайли `area_{la}_{lo}.geojson`
(сітка 0.02°) на CDN. Замінює тестове runtime-Overpass-джерело (D24) перед релізом.

Комбінований тайл = **ODbL** (share-alike). Атрибуція: **© OpenStreetMap contributors · © Kartverket (Matrikkelen, CC BY 4.0)**.

## Передумови
```
pip install pyproj boto3          # pyproj — репроєкція 25833→4326; boto3 — заливка R2
```

## Флоу (per регіон)

### 1. Matrikkelen-Bygningspunkt (тип + bygningsnummer + точка), per kommune
Прямий Geonorge-URL (Ø→O у назві; order-flow API таймаутить — прямий працює):
```
https://nedlasting.geonorge.no/geonorge/Basisdata/MatrikkelenBygning/GML/Basisdata_{NR}_{Name}_25833_MatrikkelenBygning_GML.zip
# 1577 Volda, 1520 Orsta. Розпакувати -> *.gml (EPSG:25833, ~11k буд./kommune)
```

### 2. OSM будинки + дороги, per kommune
```
python fetch_osm.py 1577 osm_volda.json      # Overpass area-query по ref=kommune
python fetch_osm.py 1520 osm_orsta.json
```

### 3. Join → тайли (Matrikkelen + OSM → point-in-polygon → D6-accessible → 0.02°)
```
python build_tiles.py OUTDIR REF_LAT  GML1 OSM1  [GML2 OSM2 ...]
# приклад (Volda+Ørsta, один прохід — union на межі):
python build_tiles.py ./tiles 62.15 \
  volda.gml osm_volda.json  orsta.gml osm_orsta.json
```
Вихід: `area_{la}_{lo}.geojson` (props: `building_id`=`m<bygningsnummer>`|`w<osmid>`, `type` [6 категорій], `accessible` [D6]) + `manifest.json`.
Ключ тайла ЗБІГАЄТЬСЯ з `AreaCache.keyFor` (0.02°) — тайли лягають у наявний on-demand механізм.

### 4. Gzip (R2 сам НЕ стискає — передстискаємо)
```
mkdir tiles-gz && for f in tiles/*.geojson; do gzip -9 -c "$f" > "tiles-gz/$(basename $f)"; done
```

### 5. Заливка на Cloudflare R2
Cloudflare: R2 → Create bucket `streif-tiles` (Location hint WEUR, Standard) → Settings → Public Development URL → Enable.
API-token: Account API Token, Object Read & Write, scope=streif-tiles → Access Key + Secret + Account ID.
```
R2_ACCOUNT_ID=... R2_ACCESS_KEY=... R2_SECRET_KEY=... \
  python upload_r2.py ./tiles-gz
# ставить Content-Type: application/json, Content-Encoding: gzip, Cache-Control
```

### 6. Увімкнути в застосунку
`app/build.gradle.kts` defaultConfig:
```
buildConfigField("boolean", "USE_CDN", "true")
buildConfigField("String", "CDN_BASE_URL", "\"https://pub-<hash>.r2.dev\"")
```
`CdnGeoJsonAreaSource` будує `$CDN_BASE_URL/area_{la}_{lo}.geojson`. `USE_CDN=false` → runtime-Overpass (dogfood).

## bygningstype → 6 категорій Streif (у `build_tiles.py::category`)
| Код | Категорія |
|---|---|
| 161–172 | hytte (fritidsbolig/seter/koie) |
| 181–183, 231–249, 431–449 | outbuilding (garasje/uthus/naust/fjøs/hangar) |
| 671–679 | sacral (kirke/kapell/bedehus) — NB: 66x = культура, не церкви |
| решта 100–199 | housing |
| 300–599, 600–669, 700–899 | public |
| 2xx, 999 | other |

## Продакшн-TODO (D31)
- **Eligibility → Elveg** (зараз `accessible` рахується з OSM-highway; Elveg = чистіша CC-BY-сумісна ліцензія).
- **Custom domain** `tiles.streif.no` перед першим зовнішнім тестером (r2.dev — dev-only, rate-limited) → потім вимкнути r2.dev + Smart Tiered Cache.
- **FKB-геометрія** через публічного партнера (kommune/fylkeskommune/Høgskulen) — апгрейд без зміни архітектури (Matrikkelen-номер як стабільний id).
- **Overpass-era розкриття** — одноразово стерти (dogfood; `source` у Room розрізняє osm/matrikkelen).
